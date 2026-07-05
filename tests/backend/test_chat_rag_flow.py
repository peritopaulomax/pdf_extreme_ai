from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass, field

import pytest

import api.chat as chat_api
import services.chat_service as chat_service
import services.stack_manager as stack_manager
from auth import store as auth_store
from fastapi.testclient import TestClient
from main import app
from project_store import ProjectStore


@pytest.fixture
def authenticated_client():
    auth_store.salvar_admins(["alice"])
    auth_store.cadastrar_senha_usuario("alice", "Alice1234")

    ps = ProjectStore(str(sys.modules["os"].environ["PROJECTS_REGISTRY_PATH"]))
    project = ps.create_project("Projeto Chat", owner_id="alice")

    client = TestClient(app)
    login = client.post("/auth/login", json={"usuario": "alice", "senha": "Alice1234"})
    assert login.status_code == 200
    return client, project.project_id


def _parse_sse_events(lines: list[str]) -> list[tuple[str, dict]]:
    raw = "".join(lines)
    events: list[tuple[str, dict]] = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        name = "message"
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        events.append((name, json.loads(data)))
    return events


def test_chat_api_returns_sse_and_delegates_workspace(authenticated_client, monkeypatch):
    client, project_id = authenticated_client
    captured: dict[str, str] = {}
    monkeypatch.delenv("CHAT_ASYNC_TURNS", raising=False)
    monkeypatch.setattr(chat_api, "chat_async_turns_enabled", lambda: False)

    def fake_run_chat_turn(**kwargs):
        captured.update(kwargs)
        yield 'event: done\ndata: {"assistant_text": "ok", "conversation_id": "c1"}\n\n'

    monkeypatch.setattr(chat_api, "bootstrap_legacy", lambda: None)
    monkeypatch.setattr(chat_api, "require_project", lambda user, pid: None)
    monkeypatch.setattr(chat_api, "run_chat_turn", fake_run_chat_turn)

    response = client.post(
        f"/projects/{project_id}/chat/rag",
        json={"message": "teste de chat", "conversation_id": None},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert "event: done" in response.text
    assert captured["workspace"] == "rag"


def test_chat_api_supports_free_workspace(authenticated_client, monkeypatch):
    client, project_id = authenticated_client
    captured: dict[str, str] = {}
    monkeypatch.delenv("CHAT_ASYNC_TURNS", raising=False)
    monkeypatch.setattr(chat_api, "chat_async_turns_enabled", lambda: False)

    def fake_run_chat_turn(**kwargs):
        captured.update(kwargs)
        yield 'event: done\ndata: {"assistant_text": "ok", "conversation_id": "c1"}\n\n'

    monkeypatch.setattr(chat_api, "bootstrap_legacy", lambda: None)
    monkeypatch.setattr(chat_api, "require_project", lambda user, pid: None)
    monkeypatch.setattr(chat_api, "run_chat_turn", fake_run_chat_turn)

    monkeypatch.delenv("CHAT_ASYNC_TURNS", raising=False)

    response = client.post(
        f"/projects/{project_id}/chat/free",
        json={"message": "teste de chat livre", "conversation_id": None},
    )

    assert response.status_code == 200
    assert captured["workspace"] == "free"


def test_legacy_sync_sse_still_works_when_feature_flag_off(authenticated_client, monkeypatch):
    client, project_id = authenticated_client
    monkeypatch.delenv("CHAT_ASYNC_TURNS", raising=False)
    called = {"sync": False}

    def fake_run_chat_turn(**kwargs):
        called["sync"] = True
        yield 'event: done\ndata: {"assistant_text": "legado", "conversation_id": "c1"}\n\n'

    monkeypatch.setattr(chat_api, "bootstrap_legacy", lambda: None)
    monkeypatch.setattr(chat_api, "require_project", lambda user, pid: None)
    monkeypatch.setattr(chat_api, "run_chat_turn", fake_run_chat_turn)
    monkeypatch.setattr(
        chat_api,
        "start_async_chat_turn",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("async nao deve ser chamado")),
    )

    response = client.post(
        f"/projects/{project_id}/chat/rag",
        json={"message": "legado", "conversation_id": None},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert called["sync"] is True


def _install_chat_legacy_fakes(monkeypatch, *, should_retry: bool = False, validation_issues=None):
    validation_issues = validation_issues or []
    saved: dict[str, object] = {}

    @dataclass
    class ConversationRecord:
        conversation_id: str
        title: str = "Nova conversa"
        model_name: str = ""
        messages: list[dict] = field(default_factory=list)

    conversation_store = types.ModuleType("conversation_store")

    def create(project_id: str, title: str, model_name: str):
        rec = ConversationRecord(conversation_id="conv-1", title=title, model_name=model_name, messages=[])
        saved["record"] = rec
        return rec

    def load(project_id: str, conversation_id: str):
        return saved.get("record")

    def save(project_id: str, record):
        saved["saved_record"] = record

    conversation_store.create = create
    conversation_store.load = load
    conversation_store.save = save
    monkeypatch.setitem(sys.modules, "conversation_store", conversation_store)

    project_memory = types.ModuleType("project_memory")
    project_memory.load = lambda project_id: "Memória do projeto"
    monkeypatch.setitem(sys.modules, "project_memory", project_memory)

    app_workspace = types.ModuleType("app_workspace")
    app_workspace.chat_mode_for_workspace = lambda workspace: "rag" if workspace == "rag" else "general"
    app_workspace.should_run_audit_synthesis = lambda *args, **kwargs: False
    monkeypatch.setitem(sys.modules, "app_workspace", app_workspace)

    audit_synthesis = types.ModuleType("audit_synthesis")
    audit_synthesis.run_audit_synthesis = lambda *args, **kwargs: "síntese auditoria"
    monkeypatch.setitem(sys.modules, "audit_synthesis", audit_synthesis)

    answer_validator = types.ModuleType("answer_validator")

    @dataclass
    class ValidationResult:
        ok: bool
        level: str
        issues: list[str]
        should_retry: bool
        retry_hint: str | None

    answer_validator.validate_answer = lambda answer, diagnostics, validation_level, user_query=None: ValidationResult(
        ok=not should_retry,
        level=validation_level,
        issues=list(validation_issues),
        should_retry=should_retry,
        retry_hint="Amplie o retrieval" if should_retry else None,
    )
    answer_validator.build_retry_prompt = lambda prompt, validation: f"{prompt}\n\nRETRY"
    monkeypatch.setitem(sys.modules, "answer_validator", answer_validator)

    chat_memory = types.ModuleType("chat_memory")
    chat_memory.rehydrate_memory_from_messages = lambda memory, messages, **kwargs: None
    chat_memory.sync_memory_with_session = lambda memory, messages, **kwargs: None
    monkeypatch.setitem(sys.modules, "chat_memory", chat_memory)

    chat_response_utils = types.ModuleType("chat_response_utils")
    chat_response_utils.coalesce_assistant_reply = (
        lambda assistant_text, stream_resp, chat_engine, wait_history=True: assistant_text
        or getattr(stream_resp, "response", "")
        or getattr(stream_resp, "unformatted_response", "")
        or ""
    )
    chat_response_utils.is_empty_llm_output = lambda text: (
        not str(text or "").strip() or str(text or "").strip().lower() == "empty response"
    )
    monkeypatch.setitem(sys.modules, "chat_response_utils", chat_response_utils)

    exhaustive = types.ModuleType("exhaustive_retrieval")
    exhaustive.format_audit_context = lambda pages: "audit context"
    exhaustive.search_exhaustive = lambda *args, **kwargs: ([], [])
    monkeypatch.setitem(sys.modules, "exhaustive_retrieval", exhaustive)

    llama_memory = types.ModuleType("llama_index.core.memory")

    class Memory:
        @staticmethod
        def from_defaults(token_limit: int):
            return types.SimpleNamespace(token_limit=token_limit)

    llama_memory.Memory = Memory
    monkeypatch.setitem(sys.modules, "llama_index.core.memory", llama_memory)

    llama_schema = types.ModuleType("llama_index.core.schema")

    class QueryBundle:
        def __init__(self, query_str: str):
            self.query_str = query_str

    class MetadataMode:
        NONE = "none"

    class TextNode:
        def __init__(self, text: str = "", metadata: dict | None = None):
            self.text = text
            self.metadata = metadata or {}

        def get_content(self, metadata_mode=None):
            return self.text

    class NodeWithScore:
        def __init__(self, node=None, score: float = 0.0):
            self.node = node or TextNode()
            self.score = score

    llama_schema.QueryBundle = QueryBundle
    llama_schema.MetadataMode = MetadataMode
    llama_schema.TextNode = TextNode
    llama_schema.NodeWithScore = NodeWithScore
    monkeypatch.setitem(sys.modules, "llama_index.core.schema", llama_schema)

    llm_thinking = types.ModuleType("llm_thinking")
    llm_thinking.clear_captured_thinking = lambda capture_llm: None
    llm_thinking.get_captured_thinking = lambda capture_llm: None
    monkeypatch.setitem(sys.modules, "llm_thinking", llm_thinking)

    query_expansion = types.ModuleType("query_expansion")
    query_expansion.expand_query = lambda query, project_memory="", intent="": query
    monkeypatch.setitem(sys.modules, "query_expansion", query_expansion)

    query_planner = types.ModuleType("query_planner")

    class QueryPlan:
        def __init__(self, profile, intent, requested_page=None, requested_page_range=None, requested_source_hint=None):
            self.profile = profile
            self.intent = intent
            self.requested_page = requested_page
            self.requested_page_range = requested_page_range
            self.requested_source_hint = requested_source_hint

    query_planner.QueryPlan = QueryPlan
    query_planner.plan_query = lambda query, settings, forced_profile=None: QueryPlan(
        profile="preciso",
        intent="padrao",
        requested_page=None,
        requested_page_range=None,
        requested_source_hint=None,
    )
    monkeypatch.setitem(sys.modules, "query_planner", query_planner)

    retrieved_chunks_ui = types.ModuleType("retrieved_chunks_ui")
    retrieved_chunks_ui.nodes_to_serializable = lambda nodes: [
        {"display_name": "Doc.pdf", "page": 182, "snippet": "Trecho relevante"}
    ]
    monkeypatch.setitem(sys.modules, "retrieved_chunks_ui", retrieved_chunks_ui)

    retrieval_pipeline = types.ModuleType("retrieval_pipeline")

    class HybridRetriever:
        def __init__(self):
            self.project_memory = ""
            self.lexical_index = object()
            self.last_diagnostics = types.SimpleNamespace(
                plan=types.SimpleNamespace(profile="preciso", intent="padrao"),
                semantic_count=4,
                lexical_count=5,
                fused_count=2,
                literal_count=5,
            )
            self.last_retrieved_nodes = ["node-a"]

        def retrieve(self, query_bundle):
            return self.last_retrieved_nodes

    retrieval_pipeline.HybridRetriever = HybridRetriever
    monkeypatch.setitem(sys.modules, "retrieval_pipeline", retrieval_pipeline)

    runtime_config = types.ModuleType("runtime_config")
    runtime_config.configure_runtime_env = lambda: types.SimpleNamespace(
        llm_default_model="gemma4:26b",
        chat_memory_token_limit=1024,
        exhaustive_batch_size=50,
        exhaustive_max_hits=250,
        audit_map_reduce_threshold=99,
        audit_pages_per_batch=10,
        analytical_map_reduce_enabled=False,
        analytical_map_reduce_min_chunks=10,
        analytical_chunks_per_batch=5,
        analytical_max_batches=6,
        low_cov_fused_threshold=0,
        auto_retry_on_low_coverage=False,
        retrieval_profiles={"preciso": types.SimpleNamespace(validation_level="light")},
    )
    monkeypatch.setitem(sys.modules, "runtime_config", runtime_config)

    return saved, retrieval_pipeline.HybridRetriever


def test_run_chat_turn_emits_status_token_meta_done_and_persists_message(monkeypatch):
    saved, hybrid_cls = _install_chat_legacy_fakes(monkeypatch)

    stack = types.SimpleNamespace(
        settings=types.SimpleNamespace(
            llm_default_model="gemma4:26b",
            chat_memory_token_limit=1024,
            exhaustive_batch_size=50,
            exhaustive_max_hits=250,
            audit_map_reduce_threshold=99,
            audit_pages_per_batch=10,
            retrieval_profiles={"preciso": types.SimpleNamespace(validation_level="light")},
        ),
        hybrid_retriever=hybrid_cls(),
        capture_llm=object(),
        chat_mode="rag",
    )

    class FakeStreamResp:
        response_gen = iter(["Primeira parte.", " Segunda parte."])
        response = "Primeira parte. Segunda parte."

    class FakeEngine:
        def stream_chat(self, prompt):
            return FakeStreamResp()

        def chat(self, prompt):
            return types.SimpleNamespace(response="Fallback")

    monkeypatch.setattr(chat_service, "bootstrap_legacy", lambda: None)
    monkeypatch.setattr(chat_service, "get_cached_stack", lambda *args, **kwargs: stack)
    monkeypatch.setattr(chat_service, "build_chat_engines", lambda *args, **kwargs: (FakeEngine(), FakeEngine()))
    monkeypatch.setattr(
        chat_service,
        "_stream_tokens",
        lambda token_gen, capture_llm, stats=None: ((piece, None) for piece in token_gen),
    )

    events = _parse_sse_events(
        list(
            chat_service.run_chat_turn(
                project_id="proj-1",
                conversation_id=None,
                message="Explique a movimentação do caso.",
                model="gemma4:26b",
                workspace="rag",
            )
        )
    )

    assert [name for name, _ in events] == ["status", "token", "token", "meta", "done"]
    assert events[0][1]["message"].startswith("Recuperando contexto")
    assert events[-2][1]["retrieved_chunks"][0]["display_name"] == "Doc.pdf"
    assert events[-1][1]["assistant_text"] == "Primeira parte. Segunda parte."
    saved_record = saved["saved_record"]
    assert saved_record.messages[-1]["role"] == "assistant"
    assert "modo=rag" in saved_record.messages[-1]["telemetry"]


def test_run_chat_turn_uses_retry_prompt_when_validation_requests_retry(monkeypatch):
    saved, hybrid_cls = _install_chat_legacy_fakes(
        monkeypatch,
        should_retry=True,
        validation_issues=["Cobertura baixa (fused < 3) para esta pergunta."],
    )

    stack = types.SimpleNamespace(
        settings=types.SimpleNamespace(
            llm_default_model="gemma4:26b",
            chat_memory_token_limit=1024,
            exhaustive_batch_size=50,
            exhaustive_max_hits=250,
            audit_map_reduce_threshold=99,
            audit_pages_per_batch=10,
            retrieval_profiles={"preciso": types.SimpleNamespace(validation_level="light")},
        ),
        hybrid_retriever=hybrid_cls(),
        capture_llm=object(),
        chat_mode="rag",
    )

    class FakeStreamResp:
        response_gen = iter(["Resposta inicial."])
        response = "Resposta inicial."

    class FakeRetryStreamResp:
        response_gen = iter(["Resposta corrigida ", "[Doc.pdf, pag. 188]"])
        response = "Resposta corrigida [Doc.pdf, pag. 188]"

    class FakeEngine:
        def stream_chat(self, prompt):
            if prompt.endswith("RETRY"):
                return FakeRetryStreamResp()
            return FakeStreamResp()

        def chat(self, prompt):
            assert prompt.endswith("RETRY")
            return types.SimpleNamespace(response="Resposta corrigida [Doc.pdf, pag. 188]")

    monkeypatch.setattr(chat_service, "bootstrap_legacy", lambda: None)
    monkeypatch.setattr(chat_service, "get_cached_stack", lambda *args, **kwargs: stack)
    monkeypatch.setattr(chat_service, "build_chat_engines", lambda *args, **kwargs: (FakeEngine(), FakeEngine()))
    monkeypatch.setattr(
        chat_service,
        "_stream_tokens",
        lambda token_gen, capture_llm, stats=None: ((piece, None) for piece in token_gen),
    )

    events = _parse_sse_events(
        list(
            chat_service.run_chat_turn(
                project_id="proj-1",
                conversation_id=None,
                message="Faça um histórico narrativo do caso.",
                model="gemma4:26b",
                workspace="rag",
            )
        )
    )

    assert events[-2][1]["validation_issues"] == ["Cobertura baixa (fused < 3) para esta pergunta."]
    assert "fallback=on" in events[-2][1]["telemetry"]
    assert "validacao: Cobertura baixa (fused < 3) para esta pergunta." in events[-2][1]["telemetry"]
    assert "gen=" in events[-2][1]["telemetry"]
    retry_status = next(
        payload for name, payload in events if name == "status" and "validacao" in payload.get("message", "").lower()
    )
    assert retry_status.get("reset_stream") is True
    assert events[-1][1]["assistant_text"] == "Resposta corrigida [Doc.pdf, pag. 188]"
    assert saved["saved_record"].messages[-1]["content"] == "Resposta corrigida [Doc.pdf, pag. 188]"


def test_run_chat_turn_preserves_initial_answer_when_retry_start_times_out(monkeypatch):
    saved, hybrid_cls = _install_chat_legacy_fakes(
        monkeypatch,
        should_retry=True,
        validation_issues=["Cobertura baixa (fused < 3) para esta pergunta."],
    )

    stack = types.SimpleNamespace(
        settings=types.SimpleNamespace(
            llm_default_model="gemma4:26b",
            chat_memory_token_limit=1024,
            exhaustive_batch_size=50,
            exhaustive_max_hits=250,
            audit_map_reduce_threshold=99,
            audit_pages_per_batch=10,
            retrieval_profiles={"preciso": types.SimpleNamespace(validation_level="light")},
        ),
        hybrid_retriever=hybrid_cls(),
        capture_llm=object(),
        chat_mode="rag",
    )

    class FakeStreamResp:
        response_gen = iter(["Resposta inicial."])
        response = "Resposta inicial."

    class FakeEngine:
        def stream_chat(self, prompt):
            return FakeStreamResp()

        def chat(self, prompt):
            return types.SimpleNamespace(response="Fallback")

    def fake_call_with_timeout(fn, timeout_s, label):
        if label == "retry_stream_start":
            raise TimeoutError("Timeout ao iniciar retry_stream_start (120s).")
        return fn()

    monkeypatch.setattr(chat_service, "bootstrap_legacy", lambda: None)
    monkeypatch.setattr(chat_service, "get_cached_stack", lambda *args, **kwargs: stack)
    monkeypatch.setattr(chat_service, "build_chat_engines", lambda *args, **kwargs: (FakeEngine(), FakeEngine()))
    monkeypatch.setattr(chat_service, "_call_with_timeout", fake_call_with_timeout)
    monkeypatch.setattr(
        chat_service,
        "_stream_tokens",
        lambda token_gen, capture_llm, stats=None: ((piece, None) for piece in token_gen),
    )

    events = _parse_sse_events(
        list(
            chat_service.run_chat_turn(
                project_id="proj-1",
                conversation_id=None,
                message="Faça um histórico narrativo do caso.",
                model="gemma4:26b",
                workspace="rag",
            )
        )
    )

    assert events[-1][0] == "done"
    assert events[-1][1]["assistant_text"] == "Resposta inicial."
    assert events[-1][1]["interrupted"] is True
    assert "retry_stream_start" in events[-1][1]["interruption_reason"]
    assert saved["saved_record"].messages[-1]["content"] == "Resposta inicial."


def test_run_chat_turn_emits_done_interrupted_with_partial_text(monkeypatch):
    saved, hybrid_cls = _install_chat_legacy_fakes(monkeypatch)

    stack = types.SimpleNamespace(
        settings=types.SimpleNamespace(
            llm_default_model="gemma4:26b",
            chat_memory_token_limit=1024,
            exhaustive_batch_size=50,
            exhaustive_max_hits=250,
            audit_map_reduce_threshold=99,
            audit_pages_per_batch=10,
            retrieval_profiles={"preciso": types.SimpleNamespace(validation_level="light")},
        ),
        hybrid_retriever=hybrid_cls(),
        capture_llm=object(),
        chat_mode="rag",
    )

    class FakeStreamResp:
        response_gen = iter(["Parte inicial."])
        response = "Parte inicial."

    class FakeEngine:
        def stream_chat(self, prompt):
            return FakeStreamResp()

        def chat(self, prompt):
            return types.SimpleNamespace(response="Fallback")

    monkeypatch.setattr(chat_service, "bootstrap_legacy", lambda: None)
    monkeypatch.setattr(chat_service, "get_cached_stack", lambda *args, **kwargs: stack)
    monkeypatch.setattr(chat_service, "build_chat_engines", lambda *args, **kwargs: (FakeEngine(), FakeEngine()))

    def fake_stream_with_timeout(*args, **kwargs):
        yield ("Parte inicial.", None)
        raise TimeoutError("Sem tokens por 90s; stream interrompido.")

    monkeypatch.setattr(chat_service, "_stream_tokens_with_idle_timeout", fake_stream_with_timeout)

    events = _parse_sse_events(
        list(
            chat_service.run_chat_turn(
                project_id="proj-1",
                conversation_id=None,
                message="Explique os ofícios.",
                model="gemma4:26b",
                workspace="rag",
            )
        )
    )

    assert [name for name, _ in events] == ["status", "token", "meta", "done"]
    assert events[-1][1]["assistant_text"] == "Parte inicial."
    assert events[-1][1]["interrupted"] is True
    assert "stream interrompido" in events[-1][1]["interruption_reason"].lower()
    assert saved["saved_record"].messages[-1]["content"] == "Parte inicial."
    assert any(
        "resposta interrompida" in issue.lower()
        for issue in saved["saved_record"].messages[-1].get("validation_issues", [])
    )


def test_run_chat_turn_errors_when_stream_start_times_out(monkeypatch):
    _saved, hybrid_cls = _install_chat_legacy_fakes(monkeypatch)

    stack = types.SimpleNamespace(
        settings=types.SimpleNamespace(
            llm_default_model="gemma4:26b",
            chat_memory_token_limit=1024,
            exhaustive_batch_size=50,
            exhaustive_max_hits=250,
            audit_map_reduce_threshold=99,
            audit_pages_per_batch=10,
            retrieval_profiles={"preciso": types.SimpleNamespace(validation_level="light")},
        ),
        hybrid_retriever=hybrid_cls(),
        capture_llm=object(),
        chat_mode="rag",
    )

    class FakeEngine:
        def stream_chat(self, prompt):
            return types.SimpleNamespace(response_gen=iter(["nunca usado"]))

        def chat(self, prompt):
            return types.SimpleNamespace(response="Fallback")

    monkeypatch.setattr(chat_service, "bootstrap_legacy", lambda: None)
    monkeypatch.setattr(chat_service, "get_cached_stack", lambda *args, **kwargs: stack)
    monkeypatch.setattr(chat_service, "build_chat_engines", lambda *args, **kwargs: (FakeEngine(), FakeEngine()))
    monkeypatch.setattr(
        chat_service,
        "_call_with_timeout",
        lambda fn, timeout_s, label: (_ for _ in ()).throw(TimeoutError("Timeout ao iniciar chat_stream_start (120s).")),
    )

    events = _parse_sse_events(
        list(
            chat_service.run_chat_turn(
                project_id="proj-1",
                conversation_id=None,
                message="Pergunta inicial",
                model="gemma4:26b",
                workspace="rag",
            )
        )
    )

    assert [name for name, _ in events] == ["status", "error"]
    assert "timeout" in events[-1][1]["message"].lower()


def test_run_chat_turn_emits_error_when_model_returns_empty(monkeypatch):
    saved, hybrid_cls = _install_chat_legacy_fakes(monkeypatch)

    stack = types.SimpleNamespace(
        settings=types.SimpleNamespace(
            llm_default_model="gemma4:26b",
            chat_memory_token_limit=1024,
            exhaustive_batch_size=50,
            exhaustive_max_hits=250,
            audit_map_reduce_threshold=99,
            audit_pages_per_batch=10,
            retrieval_profiles={"preciso": types.SimpleNamespace(validation_level="light")},
        ),
        hybrid_retriever=hybrid_cls(),
        capture_llm=types.SimpleNamespace(llm=types.SimpleNamespace(thinking=True)),
        chat_mode="rag",
    )

    class FakeStreamResp:
        response_gen = iter([])
        response = ""

    class FakeEngine:
        _skip_condense = False

        def stream_chat(self, prompt):
            return FakeStreamResp()

        def chat(self, prompt):
            return types.SimpleNamespace(response="")

    monkeypatch.setattr(chat_service, "bootstrap_legacy", lambda: None)
    monkeypatch.setattr(chat_service, "get_cached_stack", lambda *args, **kwargs: stack)
    monkeypatch.setattr(chat_service, "build_chat_engines", lambda *args, **kwargs: (FakeEngine(), FakeEngine()))
    monkeypatch.setattr(
        chat_service,
        "_stream_tokens",
        lambda token_gen, capture_llm, stats=None: iter([]),
    )
    monkeypatch.setattr(
        chat_service,
        "_recover_empty_content",
        lambda *args, **kwargs: ("", None),
    )

    events = _parse_sse_events(
        list(
            chat_service.run_chat_turn(
                project_id="proj-1",
                conversation_id=None,
                message="Explique a movimentação do caso.",
                model="gemma4:26b",
                workspace="rag",
            )
        )
    )

    assert events[-1][0] == "error"
    assert "sem gerar texto" in events[-1][1]["message"].lower()
    assert "generation_diag" in events[-1][1]
    saved_record = saved["saved_record"]
    assert saved_record.messages == []


def test_run_chat_turn_skips_condense_on_repeat_question(monkeypatch):
    saved, hybrid_cls = _install_chat_legacy_fakes(monkeypatch)

    @dataclass
    class ConversationRecord:
        conversation_id: str
        title: str = "Nova conversa"
        model_name: str = ""
        messages: list[dict] = field(default_factory=list)

    prior = ConversationRecord(
        conversation_id="conv-repeat",
        messages=[
            {"role": "user", "content": "Explique a movimentação do caso."},
            {"role": "assistant", "content": "Resposta anterior."},
        ],
    )
    saved["record"] = prior

    stack = types.SimpleNamespace(
        settings=types.SimpleNamespace(
            llm_default_model="gemma4:26b",
            chat_memory_token_limit=1024,
            exhaustive_batch_size=50,
            exhaustive_max_hits=250,
            audit_map_reduce_threshold=99,
            audit_pages_per_batch=10,
            retrieval_profiles={"preciso": types.SimpleNamespace(validation_level="light")},
        ),
        hybrid_retriever=hybrid_cls(),
        capture_llm=object(),
        chat_mode="rag",
    )

    class FakeStreamResp:
        response_gen = iter(["Resposta repetida."])
        response = "Resposta repetida."

    class FakeEngine:
        _skip_condense = False

        def stream_chat(self, prompt):
            return FakeStreamResp()

        def chat(self, prompt):
            return types.SimpleNamespace(response="Fallback")

    monkeypatch.setattr(chat_service, "bootstrap_legacy", lambda: None)
    monkeypatch.setattr(chat_service, "get_cached_stack", lambda *args, **kwargs: stack)
    monkeypatch.setattr(chat_service, "build_chat_engines", lambda *args, **kwargs: (FakeEngine(), FakeEngine()))
    monkeypatch.setattr(
        chat_service,
        "_stream_tokens",
        lambda token_gen, capture_llm, stats=None: ((piece, None) for piece in token_gen),
    )

    events = _parse_sse_events(
        list(
            chat_service.run_chat_turn(
                project_id="proj-1",
                conversation_id="conv-repeat",
                message="Explique a movimentação do caso.",
                model="gemma4:26b",
                workspace="rag",
            )
        )
    )

    status_messages = [payload["message"] for name, payload in events if name == "status"]
    assert any("condensacao" in msg.lower() for msg in status_messages)
    assert not any("validacao" in msg.lower() for msg in status_messages)
    assert events[-1][1]["assistant_text"] == "Resposta repetida."
    assert saved["saved_record"].messages[-1]["content"] == "Resposta repetida."


def test_get_cached_stack_uses_cache_until_invalidation(monkeypatch):
    calls: list[tuple] = []

    def fake_load(selected_model, forced_profile, project_id, chat_mode, workspace):
        calls.append((selected_model, forced_profile, project_id, chat_mode, workspace))
        return {"selected_model": selected_model, "project_id": project_id}

    stack_manager.invalidate_stack_cache()
    monkeypatch.setattr(stack_manager, "load_project_stack", fake_load)

    first = stack_manager.get_cached_stack("gemma4:26b", None, "p1", "rag", "rag")
    second = stack_manager.get_cached_stack("gemma4:26b", None, "p1", "rag", "rag")

    assert first == second
    assert len(calls) == 1

    stack_manager.invalidate_stack_cache()
    third = stack_manager.get_cached_stack("gemma4:26b", None, "p1", "rag", "rag")

    assert third == {"selected_model": "gemma4:26b", "project_id": "p1"}
    assert len(calls) == 2

