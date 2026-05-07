import { apiClient } from './client';

export type BackupFormat = 'xlsx' | 'csv' | 'json';

export interface ImportRowIssue {
  rowNumber: number;
  field?: string | null;
  code: string;
  message: string;
  severity: 'error' | 'warning';
}

export interface ImportPreviewRow {
  rowNumber: number;
  data: Record<string, unknown>;
  errors: ImportRowIssue[];
  warnings: ImportRowIssue[];
}

export interface ImportPreviewResult {
  totalRows: number;
  validRows: number;
  invalidRows: number;
  rows: ImportPreviewRow[];
  errors: ImportRowIssue[];
}

export interface ImportConfirmResult {
  importedCount: number;
  skippedCount: number;
  errors: ImportRowIssue[];
}

interface ApiImportRowIssue {
  row_number: number;
  field?: string | null;
  code: string;
  message: string;
  severity: 'error' | 'warning';
}

interface ApiImportPreviewRow {
  row_number: number;
  data: Record<string, unknown>;
  errors: ApiImportRowIssue[];
  warnings: ApiImportRowIssue[];
}

interface ApiImportPreviewResult {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  rows: ApiImportPreviewRow[];
  errors: ApiImportRowIssue[];
}

interface ApiImportConfirmResult {
  imported_count: number;
  skipped_count: number;
  errors: ApiImportRowIssue[];
}

function normalizeIssue(issue: ApiImportRowIssue): ImportRowIssue {
  return {
    rowNumber: issue.row_number,
    field: issue.field,
    code: issue.code,
    message: issue.message,
    severity: issue.severity,
  };
}

function normalizePreview(data: ApiImportPreviewResult): ImportPreviewResult {
  return {
    totalRows: data.total_rows,
    validRows: data.valid_rows,
    invalidRows: data.invalid_rows,
    rows: data.rows.map((row) => ({
      rowNumber: row.row_number,
      data: row.data,
      errors: row.errors.map(normalizeIssue),
      warnings: row.warnings.map(normalizeIssue),
    })),
    errors: data.errors.map(normalizeIssue),
  };
}

function normalizeConfirm(data: ApiImportConfirmResult): ImportConfirmResult {
  return {
    importedCount: data.imported_count,
    skippedCount: data.skipped_count,
    errors: data.errors.map(normalizeIssue),
  };
}

function buildImportForm(file: File, format: BackupFormat): FormData {
  const data = new FormData();
  data.append('file', file);
  data.append('format', format);
  return data;
}

function inferFilename(headers: { [key: string]: unknown }, fallback: string): string {
  const rawDisposition = headers['content-disposition'];
  const disposition = typeof rawDisposition === 'string' ? rawDisposition : '';
  const match = disposition.match(/filename="([^"]+)"/);
  return match?.[1] || fallback;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function downloadBooksExport(format: BackupFormat): Promise<void> {
  const response = await apiClient.get<Blob>('/books/export', {
    params: { format },
    responseType: 'blob',
  });
  downloadBlob(response.data, inferFilename(response.headers, `books.${format}`));
}

export async function downloadImportTemplate(format: BackupFormat): Promise<void> {
  const response = await apiClient.get<Blob>('/books/import/template', {
    params: { format },
    responseType: 'blob',
  });
  downloadBlob(response.data, inferFilename(response.headers, `books_import_template.${format}`));
}

export async function previewBooksImport(file: File, format: BackupFormat): Promise<ImportPreviewResult> {
  const { data } = await apiClient.post<ApiImportPreviewResult>('/books/import/preview', buildImportForm(file, format), {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return normalizePreview(data);
}

export async function confirmBooksImport(file: File, format: BackupFormat): Promise<ImportConfirmResult> {
  const { data } = await apiClient.post<ApiImportConfirmResult>('/books/import', buildImportForm(file, format), {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return normalizeConfirm(data);
}
