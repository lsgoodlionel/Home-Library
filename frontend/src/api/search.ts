import { apiClient } from './client';
import type { ImportResultPayload, SearchResultItem, SearchResultsResponse } from '@/types/search';

interface ApiSearchResultItem {
  source: string;
  source_id: string;
  title: string;
  subtitle?: string;
  author?: string;
  publisher?: string;
  publish_year?: number | null;
  isbn?: string;
  cover_url?: string;
  summary?: string;
  language?: string;
  pages?: number | null;
  raw?: Record<string, unknown>;
}

interface ApiSearchResultsResponse {
  items: ApiSearchResultItem[];
}

function normalizeSearchResultItem(item: ApiSearchResultItem): SearchResultItem {
  return {
    source: item.source,
    sourceId: item.source_id,
    title: item.title,
    subtitle: item.subtitle || '',
    author: item.author || '',
    publisher: item.publisher || '',
    publishYear: item.publish_year ?? null,
    isbn: item.isbn || '',
    coverUrl: item.cover_url || '',
    summary: item.summary || '',
    language: item.language || '',
    pages: item.pages ?? null,
    raw: item.raw,
  };
}

export async function searchBooks(
  query: string,
  limit = 30,
  options?: { mode?: string; provider?: string },
): Promise<SearchResultItem[]> {
  const { data } = await apiClient.get<ApiSearchResultsResponse>('/search/books', {
    params: {
      query,
      limit,
      ...(options?.mode && { mode: options.mode }),
      ...(options?.provider && { provider: options.provider }),
    },
  });
  return data.items.map(normalizeSearchResultItem);
}

export async function searchByISBN(isbn: string): Promise<SearchResultItem[]> {
  const { data } = await apiClient.get<ApiSearchResultsResponse>(`/search/isbn/${encodeURIComponent(isbn)}`);
  return data.items.map(normalizeSearchResultItem);
}

export async function importSearchResult(payload: ImportResultPayload): Promise<void> {
  await apiClient.post('/search/import-result', {
    result: payload.result,
    category_id: payload.categoryId ?? null,
    location_id: payload.locationId ?? null,
    import_mode: payload.importMode,
  });
}
