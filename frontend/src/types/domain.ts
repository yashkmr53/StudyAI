import type { ModuleId } from "./modules";

/**
 * Workspace domain model for the UI.
 *
 * Deliberately storage-agnostic: components consume these types via
 * repositories/stores and never talk to HTTP or IndexedDB directly.
 */

/* ---- Subjects ---- */

export interface SubjectSummary extends SubjectBase {
  noteCount: number;
  folderCount: number;
  lastOpenedAt: string | null;
}

export interface SubjectBase {
  id: string;
  name: string;
  createdAt?: string;
}

/* ---- Folders (represented by the Notebook entity) ---- */

export interface FolderNode {
  /** Notebook id from the backend. */
  id: string;
  subjectId: string;
  parentId: string | null;
  name: string;
  createdAt?: string;
  updatedAt?: string;
}

/** Virtual bucket for notes written without choosing a folder (§13). */
export const UNFILED_FOLDER_ID = "__unfiled__";

export function isUnfiledFolder(folderId: string): boolean {
  return folderId === UNFILED_FOLDER_ID;
}

/* ---- Notes ---- */

export type NoteSourceKind = "canvas" | "upload";

/**
 * A note is one handwritten study artifact: its source pages (canvas
 * strokes or an uploaded scan) plus its faithful transcription and any
 * generated enrichment hanging off it.
 */
export interface NoteMeta {
  /** Canvas session id or document id, depending on source kind. */
  id: string;
  refId: string;
  profileId: string;
  subjectId: string;
  /** Folder id, or null while unfiled. */
  folderId: string | null;
  title: string;
  source: NoteSourceKind;
  createdAt: string;
  updatedAt: string;
}

export type TranscriptionStatus = "pending" | "processing" | "transcribed" | "failed";

export type EnrichmentState =
  | "not_enriched"
  | "enriching"
  | "enriched"
  | "out_of_date"
  | "failed";

/** Status chip model per active module (§14). */
export type NoteStatusChip =
  | { kind: "transcription"; value: TranscriptionStatus }
  | { kind: "enrichment"; value: EnrichmentState };

/* ---- Handwritten view ---- */

export interface SourcePageRef {
  pageNumber: number;
}

/* ---- Chat ---- */

export interface CitationRef {
  page: number;
  bbox?: number[] | null;
}

export interface ChatCitation {
  /** Stable internal source ID assigned by the backend (e.g. "src-001"). */
  source_id?: string;
  /** "database" | "web" */
  source_type: string;
  chunk_id?: string;
  document_id?: string;
  /** Human-readable document title, e.g. "DSA Notes — Dynamic Programming" */
  document_title?: string | null;
  /** Subject / topic name from the user's curriculum */
  subject_name?: string | null;
  page_start?: number;
  page_end?: number;
  snippet?: string;
  rrf_score?: number;
  /** Web-specific fields */
  url?: string | null;
  /** Web page title (for web sources) */
  title?: string | null;
  /** Domain of the web source, e.g. "docs.python.org" */
  domain?: string | null;
}

/* ---- Enriched view ---- */

export interface EnrichedBlock {
  index: number;
  title: string;
  content: string;
  citations: CitationRef[];
}

export interface EnrichmentSnapshot {
  state: EnrichmentState;
  blocks: EnrichedBlock[];
  generatedAt: string | null;
}

/* ---- Practice QA / Tests / Chat DTOs used by UI ---- */

export interface PracticeQuestion {
  id: string;
  documentId: string;
  prompt: string;
  options: string[];
  answerIndex: number;
  answerText: string;
  difficulty: "easy" | "medium" | "hard";
  stale: boolean;
}

export interface ChatThreadSummary {
  id: string;
  title: string;
  subjectId: string | null;
  createdAt?: string;
}

export interface ChatMessageItem {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: ChatCitation[];
  pending?: boolean;
}

export interface TestAttemptQuestion {
  id: string;
  prompt: string;
  options: string[];
  answerIndex: number | null;
}

export interface TestSummary {
  id: string;
  title: string;
  subjectId: string | null;
  questionCount: number;
  status: "draft" | "ready" | "completed";
  mastery?: number | null;
  createdAt?: string;
}

export interface ActiveModuleInfo {
  moduleId: ModuleId;
}
