export type BookStatus = 'available' | 'borrowed' | 'lost' | 'pending' | 'gifted';
export type ReadStatus = 'unread' | 'reading' | 'read' | 'paused';
export type BookSource = 'manual' | 'isbn_lookup' | 'title_search' | 'ollama' | 'import';

export interface CategoryOption {
  id: number;
  code: string;
  name: string;
  parentId: number | null;
  description?: string;
  sortOrder?: number;
  isSystem?: boolean;
  children?: CategoryOption[];
}

export interface LocationOption {
  id: number;
  room: string;
  shelf: string;
  layer?: string;
  position?: string;
  fullPath: string;
  description?: string;
  sortOrder?: number;
}

export interface BookTag {
  id?: number;
  name: string;
  color?: string;
}

export interface BookListItem {
  id: number;
  title: string;
  subtitle: string;
  author: string;
  publisher: string;
  publishYear: number | null;
  isbn: string;
  coverUrl: string;
  category: CategoryOption | null;
  location: Pick<LocationOption, 'id' | 'fullPath'> | null;
  status: BookStatus;
  readStatus: ReadStatus;
  rating: number | null;
  isFavorite: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface BookDetail extends BookListItem {
  translator: string;
  originalIsbn: string;
  language: string;
  pages: number | null;
  priceCents: number | null;
  binding: string;
  series: string;
  summary: string;
  authorIntro: string;
  tags: BookTag[];
  source: BookSource;
  note: string;
  categoryId: number | null;
  locationId: number | null;
}

export interface BookQuery {
  page: number;
  pageSize: number;
  keyword?: string;
  categoryId?: number;
  locationId?: number;
  status?: BookStatus;
  readStatus?: ReadStatus;
  isFavorite?: boolean;
}

export interface PaginatedBooks {
  items: BookListItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface BookFormModel {
  title: string;
  subtitle: string;
  author: string;
  translator: string;
  publisher: string;
  publishYear: number | null;
  isbn: string;
  language: string;
  pages: number | null;
  priceCents: number | null;
  binding: string;
  series: string;
  coverUrl: string;
  summary: string;
  authorIntro: string;
  categoryId: number | null;
  locationId: number | null;
  tagNames: string[];
  status: BookStatus;
  readStatus: ReadStatus;
  rating: number | null;
  isFavorite: boolean;
  note: string;
}

export interface BookBatchUpdatePayload {
  bookIds: number[];
  updates: Partial<Pick<BookFormModel, 'categoryId' | 'locationId' | 'status' | 'readStatus' | 'tagNames'>>;
}

export const BOOK_STATUS_OPTIONS: Array<{ label: string; value: BookStatus }> = [
  { label: '在架', value: 'available' },
  { label: '借出', value: 'borrowed' },
  { label: '遗失', value: 'lost' },
  { label: '待整理', value: 'pending' },
  { label: '已转赠', value: 'gifted' },
];

export const READ_STATUS_OPTIONS: Array<{ label: string; value: ReadStatus }> = [
  { label: '未读', value: 'unread' },
  { label: '阅读中', value: 'reading' },
  { label: '已读', value: 'read' },
  { label: '暂停', value: 'paused' },
];

export function createEmptyBookForm(): BookFormModel {
  return {
    title: '',
    subtitle: '',
    author: '',
    translator: '',
    publisher: '',
    publishYear: null,
    isbn: '',
    language: 'zh-CN',
    pages: null,
    priceCents: null,
    binding: '',
    series: '',
    coverUrl: '',
    summary: '',
    authorIntro: '',
    categoryId: null,
    locationId: null,
    tagNames: [],
    status: 'available',
    readStatus: 'unread',
    rating: null,
    isFavorite: false,
    note: '',
  };
}
