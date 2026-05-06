export interface SearchResultItem {
  source: string;
  sourceId: string;
  title: string;
  subtitle: string;
  author: string;
  publisher: string;
  publishYear: number | null;
  isbn: string;
  coverUrl: string;
  summary: string;
  language: string;
  pages: number | null;
  raw?: Record<string, unknown>;
}

export interface SearchResultsResponse {
  items: SearchResultItem[];
}

export interface ImportResultPayload {
  result: Record<string, unknown>;
  categoryId?: number | null;
  locationId?: number | null;
  importMode: 'draft' | 'create';
}
