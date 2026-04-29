import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingest_service import run_ingest
from project_store import ProjectStore, apply_project_settings
from runtime_config import configure_runtime_env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingestao de PDFs no Qdrant")
    parser.add_argument(
        "--data-dir",
        default="./data",
        help="Diretorio com PDFs para ingestao",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Recria a colecao antes de indexar (destrutivo)",
    )
    parser.add_argument(
        "--reprocess-all",
        action="store_true",
        help="Ignora checkpoint e reprocessa todos os PDFs do diretorio",
    )
    parser.add_argument(
        "--project-id",
        default="",
        help="ID do projeto (usa colecao/lexical/checkpoint do projeto)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = configure_runtime_env()
    if args.project_id:
        store = ProjectStore(settings.projects_registry_path)
        project = store.get_project(args.project_id.strip())
        if project is None:
            raise SystemExit(
                f"Projeto nao encontrado: {args.project_id}. "
                "Crie o projeto primeiro na UI."
            )
        settings = apply_project_settings(settings, project)
    result = run_ingest(
        settings=settings,
        data_dir=args.data_dir,
        rebuild=args.rebuild,
        reprocess_all=args.reprocess_all,
        update_checkpoint=True,
        progress_callback=lambda ev: print(ev.get("message", ev.get("stage", ""))),
    )
    print("\nINDEXACAO FINALIZADA")
    print(f"Arquivos processados: {result.files_processed}/{result.files_total}")
    print(f"Documentos de pagina processados: {result.total_pages}")
    print(f"Chunks indexados nesta execucao: {result.total_chunks}")
    if result.errors:
        print("Erros:")
        for err in result.errors:
            print(f"- {err}")


if __name__ == "__main__":
    main()
