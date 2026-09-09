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

export interface TableProposal {
  name: string
  source_filename: string
  sampled_rows: number
  columns: ColumnProposal[]
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
