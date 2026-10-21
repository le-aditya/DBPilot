/** Shapes the API returns. Kept in one place so screens cannot drift apart. */

export type ColumnType =
  | 'integer'
  | 'numeric'
  | 'boolean'
  | 'date'
  | 'timestamp'
  | 'text'

export const COLUMN_TYPES: ColumnType[] = [
  'integer',
  'numeric',
  'boolean',
  'date',
  'timestamp',
  'text',
]

export interface ColumnProposal {
  name: string
  source_name: string
  type: ColumnType
  nullable: boolean
  samples: string[]
}

export interface ColumnTypeChange {
  column: string
  was: string
  now: ColumnType
}

/** What re-uploading a file would change about the table it already built. */
export interface UploadTableDiff {
  existing: boolean
  previous_row_count: number | null
  previous_columns: string[]
  added_columns: string[]
  removed_columns: string[]
  type_changes: ColumnTypeChange[]
  unchanged: boolean
}

export interface TableProposal {
  name: string
  source_filename: string
  sampled_rows: number
  columns: ColumnProposal[]
  diff?: UploadTableDiff | null
}

export interface UploadAnalysis {
  tables: TableProposal[]
}

export interface ForeignKeySpec {
  column: string
  references_table: string
  references_column: string
}

/** A proposal plus the decisions the review screen collects. */
export interface TableSpec extends TableProposal {
  primary_key: string | null
  foreign_keys: ForeignKeySpec[]
}

export interface UploadResult {
  schema_name: string
  table_count: number
  tables: { name: string; row_count: number }[]
}

export interface SchemaColumn {
  name: string
  data_type: string
  nullable: boolean
  default: string | null
  is_primary_key: boolean
  references_table: string | null
  references_column: string | null
}

export interface SchemaIndex {
  name: string
  definition: string
}

export interface SchemaTable {
  name: string
  row_count: number
  columns: SchemaColumn[]
  indexes: SchemaIndex[]
}

export interface ProjectSchema {
  schema_name: string | null
  tables: SchemaTable[]
}

export interface TablePreviewData {
  columns: string[]
  rows: (string | number | boolean | null)[][]
  total: number
  limit: number
  offset: number
}

export interface Project {
  id: number
  name: string
  source_type: 'upload' | 'connection'
  schema_name: string | null
  table_count: number | null
  is_demo: boolean
  created_at: string
}

export type QueryStatus = 'success' | 'error' | 'blocked'

export interface ExecuteResponse {
  query_id: number
  status: QueryStatus
  columns: string[]
  rows: (string | number | boolean | null)[][]
  row_count: number
  duration_ms: number
  executed_sql: string | null
  truncated: boolean
  error: string | null
  rule: string | null
}

export interface QuestionResponse {
  sql: string
  assumptions: string[]
  confidence: string
  missing: string | null
  cached: boolean
  execution: ExecuteResponse | null
}

export interface ErdColumn {
  name: string
  data_type: string
  nullable: boolean
  is_primary_key: boolean
  is_foreign_key: boolean
}

export interface ErdNode {
  name: string
  row_count: number
  is_junction: boolean
  columns: ErdColumn[]
  x: number | null
  y: number | null
}

export type Cardinality = '1:1' | '1:N' | 'N:M'

export interface ErdEdge {
  source: string
  target: string
  source_column: string
  target_column: string
  cardinality: Cardinality
  via: string | null
}

export interface ErdResponse {
  nodes: ErdNode[]
  edges: ErdEdge[]
}

export interface ExplanationClause {
  clause: string
  text: string
  start: number
  end: number
}

export interface ExplanationResponse {
  summary: string
  clauses: ExplanationClause[]
}

export interface QuerySummary {
  id: number
  question_text: string | null
  executed_sql: string | null
  status: QueryStatus
  row_count: number | null
  duration_ms: number | null
  was_edited: boolean
  error_message: string | null
  created_at: string
}

export interface DashboardResponse {
  table_count: number
  total_rows: number
  storage_bytes: number
  queries_run: number
  queries_this_week: number
  blocked_count: number
  average_duration_ms: number | null
  slowest: QuerySummary[]
  recent: QuerySummary[]
}

export interface HistoryResponse {
  queries: QuerySummary[]
  total: number
  limit: number
  offset: number
}

export interface SavedQueryParameter {
  name: string
  type: string
  label: string
  default: string | null
}

export interface SavedQuery {
  id: number
  name: string
  sql_template: string
  parameters: SavedQueryParameter[]
  query_id: number | null
  created_at: string
}

/** One saved snapshot of a query's SQL, created each time it is edited. */
export interface SavedQueryVersion {
  id: number
  revision: number
  sql_template: string
  parameters: SavedQueryParameter[]
  created_at: string
}
