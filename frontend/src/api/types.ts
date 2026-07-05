export type ChatMode = "rag" | "free";
export type WorkspaceMode = ChatMode | "proofread";
export type ProjectTab = "chat" | "documents" | "config";

export interface AppConfig {
  llm_models: string[];
  llm_default_model: string;
  ui_ingest_max_files: number;
  ui_ingest_max_file_mb: number;
  ingest_quality_warn_threshold: number;
}

export interface ProjectDocument {
  file_id: string;
  display_name?: string;
  storage_name?: string;
  path?: string;
  sha256?: string;
  size_mb?: number;
  status?: string;
  pages?: number;
  chunks?: number;
}

export interface IngestPerFile {
  source_file?: string;
  file?: string;
  status?: string;
  quality?: number;
  pages?: number;
  chunks?: number;
}

export interface ProofreadResult {
  corrected_text: string;
  source_text?: string;
  changes: Array<{ original: string; corrected: string; reason: string }>;
  error?: string | null;
  raw_fallback?: boolean;
  raw_response?: string;
  highlighted_html?: string;
}

export interface ProjectRecord {
  project_id: string;
  name: string;
  created_at: string;
  updated_at: string;
  qdrant_collection: string;
  lexical_db_path: string;
  checkpoint_path: string;
  global_rules: string;
  documents: DocumentEntry[];
}

export interface DocumentEntry {
  file_id: string;
  display_name?: string;
  storage_name?: string;
  path?: string;
  status?: string;
  pages?: number;
  chunks?: number;
}

export type TurnStatus = "running" | "completed" | "failed" | "cancelled";

export interface ConversationRecord {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
  model_name: string;
  active_turn_id?: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  telemetry?: string;
  retrieved_chunks?: RetrievedChunk[];
  validation_issues?: string[];
  turn_id?: string;
  status?: TurnStatus;
  error?: string | null;
  updated_at?: string;
  created_at?: string;
}

export interface TurnStartResponse {
  turn_id: string;
  conversation_id: string;
}

export interface TurnSnapshotEvent {
  assistant_text: string;
  thinking?: string | null;
  status: TurnStatus;
  updated_at?: string;
  error?: string | null;
}

export interface RetrievedChunk {
  rank?: number;
  display_name?: string;
  source_file?: string;
  page?: number;
  score?: number;
  snippet?: string;
  lexical_hit?: boolean;
  parent_context?: boolean;
  page_level?: boolean;
  doc_type?: string;
  doc_number?: string;
}

export interface ChatRequestBody {
  message: string;
  conversation_id: string | null;
  model?: string | null;
  profile?: string | null;
  audit_mode?: boolean;
  deep_mode?: boolean;
  use_project_memory?: boolean;
  session_rules?: string;
}

export interface ChatMetaEvent {
  conversation_id?: string;
  telemetry?: string | null;
  retrieved_chunks?: RetrievedChunk[];
  validation_issues?: string[];
}

export interface ChatDoneEvent {
  assistant_text: string;
  thinking?: string | null;
  conversation_id: string;
  interrupted?: boolean;
  interruption_reason?: string | null;
}

export const MODEL_OPTIONS = [
  { id: "gemma4:26b", label: "gemma4:26b (default)" },
  { id: "gemma4:e4b", label: "gemma4:e4b (rápido)" },
] as const;

export const PROFILE_OPTIONS = [
  { id: "automatico", label: "Automático" },
  { id: "rapido", label: "Rápido" },
  { id: "preciso", label: "Preciso" },
  { id: "pericial", label: "Pericial" },
] as const;
