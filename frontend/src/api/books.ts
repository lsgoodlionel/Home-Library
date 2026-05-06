import { apiClient } from './client';
import type {
  BookBatchUpdatePayload,
  BookDetail,
  BookFormModel,
  BookListItem,
  BookQuery,
  CategoryOption,
  LocationOption,
  PaginatedBooks,
} from '@/types/book';

interface ApiCategory {
  id: number;
  code: string;
  name: string;
  parent_id: number | null;
  description?: string;
  sort_order?: number;
  is_system?: boolean;
  children?: ApiCategory[];
}

interface ApiLocation {
  id: number;
  room: string;
  shelf: string;
  layer?: string;
  position?: string;
  full_path: string;
  description?: string;
  sort_order?: number;
}

interface ApiBookListItem {
  id: number;
  title: string;
  subtitle?: string;
  author?: string;
  publisher?: string;
  publish_year?: number | null;
  isbn?: string;
  cover_url?: string;
  category?: ApiCategory | null;
  location?: Pick<ApiLocation, 'id' | 'full_path'> | null;
  status: BookListItem['status'];
  read_status: BookListItem['readStatus'];
  rating?: number | null;
  is_favorite?: boolean;
  created_at?: string;
  updated_at?: string;
}

interface ApiBookDetail extends ApiBookListItem {
  translator?: string;
  original_isbn?: string;
  language?: string;
  pages?: number | null;
  price_cents?: number | null;
  binding?: string;
  series?: string;
  summary?: string;
  author_intro?: string;
  tags?: Array<{ id?: number; name: string; color?: string }>;
  source?: BookDetail['source'];
  note?: string;
  category_id?: number | null;
  location_id?: number | null;
}

interface ApiPaginatedBooks {
  items: ApiBookListItem[];
  total: number;
  page: number;
  page_size: number;
}

function normalizeCategory(category: ApiCategory): CategoryOption {
  return {
    id: category.id,
    code: category.code,
    name: category.name,
    parentId: category.parent_id,
    description: category.description || '',
    sortOrder: category.sort_order || 0,
    isSystem: Boolean(category.is_system),
    children: category.children?.map(normalizeCategory) || [],
  };
}

function normalizeLocation(location: ApiLocation): LocationOption {
  return {
    id: location.id,
    room: location.room,
    shelf: location.shelf,
    layer: location.layer || '',
    position: location.position || '',
    fullPath: location.full_path,
    description: location.description || '',
    sortOrder: location.sort_order || 0,
  };
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function positiveNumberOrNull(value: number | null): number | null {
  return value !== null && value > 0 ? value : null;
}

function normalizeBookListItem(book: ApiBookListItem): BookListItem {
  return {
    id: book.id,
    title: book.title,
    subtitle: book.subtitle || '',
    author: book.author || '',
    publisher: book.publisher || '',
    publishYear: book.publish_year ?? null,
    isbn: book.isbn || '',
    coverUrl: book.cover_url || '',
    category: book.category ? normalizeCategory(book.category) : null,
    location: book.location
      ? {
          id: book.location.id,
          fullPath: book.location.full_path,
        }
      : null,
    status: book.status,
    readStatus: book.read_status,
    rating: book.rating ?? null,
    isFavorite: Boolean(book.is_favorite),
    createdAt: book.created_at || '',
    updatedAt: book.updated_at || '',
  };
}

function normalizeBookDetail(book: ApiBookDetail): BookDetail {
  const listItem = normalizeBookListItem(book);

  return {
    ...listItem,
    translator: book.translator || '',
    originalIsbn: book.original_isbn || '',
    language: book.language || '',
    pages: book.pages ?? null,
    priceCents: book.price_cents ?? null,
    binding: book.binding || '',
    series: book.series || '',
    summary: book.summary || '',
    authorIntro: book.author_intro || '',
    tags: book.tags || [],
    source: book.source || 'manual',
    note: book.note || '',
    categoryId: book.category_id ?? book.category?.id ?? null,
    locationId: book.location_id ?? book.location?.id ?? null,
  };
}

function toBookPayload(model: BookFormModel) {
  return {
    title: model.title.trim(),
    subtitle: emptyToNull(model.subtitle),
    author: emptyToNull(model.author),
    translator: emptyToNull(model.translator),
    publisher: emptyToNull(model.publisher),
    publish_year: model.publishYear,
    isbn: emptyToNull(model.isbn),
    language: emptyToNull(model.language),
    pages: positiveNumberOrNull(model.pages),
    price_cents: model.priceCents,
    binding: emptyToNull(model.binding),
    series: emptyToNull(model.series),
    cover_url: emptyToNull(model.coverUrl),
    summary: emptyToNull(model.summary),
    author_intro: emptyToNull(model.authorIntro),
    category_id: model.categoryId,
    location_id: model.locationId,
    tag_names: model.tagNames,
    status: model.status,
    read_status: model.readStatus,
    rating: positiveNumberOrNull(model.rating),
    is_favorite: model.isFavorite,
    note: emptyToNull(model.note),
  };
}

export function bookDetailToForm(book: BookDetail): BookFormModel {
  return {
    title: book.title,
    subtitle: book.subtitle,
    author: book.author,
    translator: book.translator,
    publisher: book.publisher,
    publishYear: book.publishYear,
    isbn: book.isbn,
    language: book.language || 'zh-CN',
    pages: book.pages,
    priceCents: book.priceCents,
    binding: book.binding,
    series: book.series,
    coverUrl: book.coverUrl,
    summary: book.summary,
    authorIntro: book.authorIntro,
    categoryId: book.categoryId,
    locationId: book.locationId,
    tagNames: book.tags.map((tag) => tag.name),
    status: book.status,
    readStatus: book.readStatus,
    rating: book.rating,
    isFavorite: book.isFavorite,
    note: book.note,
  };
}

export async function getBooks(query: BookQuery): Promise<PaginatedBooks> {
  const params = {
    page: query.page,
    page_size: query.pageSize,
    keyword: query.keyword || undefined,
    category_id: query.categoryId || undefined,
    location_id: query.locationId || undefined,
    status: query.status || undefined,
    read_status: query.readStatus || undefined,
    is_favorite: query.isFavorite,
  };
  const { data } = await apiClient.get<ApiPaginatedBooks>('/books', { params });

  return {
    items: data.items.map(normalizeBookListItem),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
  };
}

export async function getBook(id: number): Promise<BookDetail> {
  const { data } = await apiClient.get<ApiBookDetail>(`/books/${id}`);
  return normalizeBookDetail(data);
}

export async function createBook(payload: BookFormModel): Promise<BookDetail> {
  const { data } = await apiClient.post<ApiBookDetail>('/books', toBookPayload(payload));
  return normalizeBookDetail(data);
}

export async function updateBook(id: number, payload: BookFormModel): Promise<BookDetail> {
  const { data } = await apiClient.patch<ApiBookDetail>(`/books/${id}`, toBookPayload(payload));
  return normalizeBookDetail(data);
}

export async function deleteBook(id: number): Promise<void> {
  await apiClient.delete(`/books/${id}`);
}

export async function batchUpdateBooks(payload: BookBatchUpdatePayload): Promise<void> {
  await apiClient.post('/books/batch-update', {
    book_ids: payload.bookIds,
    updates: {
      category_id: payload.updates.categoryId,
      location_id: payload.updates.locationId,
      status: payload.updates.status,
      read_status: payload.updates.readStatus,
      tag_names: payload.updates.tagNames,
    },
  });
}

export async function getCategoryOptions(): Promise<CategoryOption[]> {
  const { data } = await apiClient.get<ApiCategory[]>('/categories');
  return data.map(normalizeCategory);
}

export async function getLocationOptions(): Promise<LocationOption[]> {
  const { data } = await apiClient.get<ApiLocation[]>('/locations');
  return data.map(normalizeLocation);
}
