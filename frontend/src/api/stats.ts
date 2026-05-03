import { apiClient } from './client';
import type {
  ActiveBorrowSummary,
  DistributionItem,
  ReadingStats,
  StatBookSummary,
  StatsOverview,
  TimelinePoint,
} from '@/types/stats';

interface ApiBookSummary {
  id?: number;
  title?: string;
  author?: string | null;
  category_name?: string | null;
  category?: { name?: string } | null;
  location_path?: string | null;
  location?: { full_path?: string } | null;
  created_at?: string;
}

interface ApiActiveBorrow {
  id?: number;
  book_id?: number;
  book_title?: string;
  book?: { id?: number; title?: string } | null;
  borrower_name?: string;
  borrowed_at?: string;
  due_at?: string | null;
}

interface ApiOverview {
  total_books?: number;
  available_books?: number;
  borrowed_books?: number;
  read_books?: number;
  unread_books?: number;
  favorite_books?: number;
  recent_books?: ApiBookSummary[];
  active_borrows?: ApiActiveBorrow[];
}

interface ApiDistributionItem {
  id?: number;
  code?: string;
  name?: string;
  label?: string;
  count?: number;
  value?: number;
}

interface ApiReadingStats {
  unread?: number;
  reading?: number;
  read?: number;
  paused?: number;
  items?: ApiDistributionItem[];
}

interface ApiTimelinePoint {
  period?: string;
  month?: string;
  year?: string | number;
  count?: number;
  value?: number;
}

function normalizeBookSummary(book: ApiBookSummary): StatBookSummary {
  return {
    id: book.id || 0,
    title: book.title || '未命名图书',
    author: book.author || '',
    categoryName: book.category_name || book.category?.name || '',
    locationPath: book.location_path || book.location?.full_path || '',
    createdAt: book.created_at || '',
  };
}

function normalizeActiveBorrow(record: ApiActiveBorrow): ActiveBorrowSummary {
  return {
    id: record.id || 0,
    bookId: record.book_id || record.book?.id || 0,
    bookTitle: record.book_title || record.book?.title || '未命名图书',
    borrowerName: record.borrower_name || '',
    borrowedAt: record.borrowed_at || '',
    dueAt: record.due_at || '',
  };
}

function normalizeDistributionItem(item: ApiDistributionItem): DistributionItem {
  return {
    id: item.id,
    code: item.code,
    name: item.name || item.label || '未分类',
    count: item.count ?? item.value ?? 0,
  };
}

function normalizeDistribution(data: ApiDistributionItem[] | { items?: ApiDistributionItem[] }): DistributionItem[] {
  const items = Array.isArray(data) ? data : data.items || [];
  return items.map(normalizeDistributionItem);
}

export async function getStatsOverview(): Promise<StatsOverview> {
  const { data } = await apiClient.get<ApiOverview>('/stats/overview');
  return {
    totalBooks: data.total_books || 0,
    availableBooks: data.available_books || 0,
    borrowedBooks: data.borrowed_books || 0,
    readBooks: data.read_books || 0,
    unreadBooks: data.unread_books || 0,
    favoriteBooks: data.favorite_books || 0,
    recentBooks: (data.recent_books || []).map(normalizeBookSummary),
    activeBorrows: (data.active_borrows || []).map(normalizeActiveBorrow),
  };
}

export async function getCategoryStats(): Promise<DistributionItem[]> {
  const { data } = await apiClient.get<ApiDistributionItem[] | { items?: ApiDistributionItem[] }>(
    '/stats/categories',
  );
  return normalizeDistribution(data);
}

export async function getLocationStats(): Promise<DistributionItem[]> {
  const { data } = await apiClient.get<ApiDistributionItem[] | { items?: ApiDistributionItem[] }>(
    '/stats/locations',
  );
  return normalizeDistribution(data);
}

export async function getReadingStats(): Promise<ReadingStats> {
  const { data } = await apiClient.get<ApiReadingStats>('/stats/reading');
  if (data.items) {
    const mapped = normalizeDistribution(data).reduce(
      (acc, item) => ({ ...acc, [item.name]: item.count }),
      {} as Record<string, number>,
    );
    return {
      unread: mapped.unread || mapped['未读'] || 0,
      reading: mapped.reading || mapped['阅读中'] || 0,
      read: mapped.read || mapped['已读'] || 0,
      paused: mapped.paused || mapped['暂停'] || 0,
    };
  }

  return {
    unread: data.unread || 0,
    reading: data.reading || 0,
    read: data.read || 0,
    paused: data.paused || 0,
  };
}

export async function getTimelineStats(): Promise<TimelinePoint[]> {
  const { data } = await apiClient.get<ApiTimelinePoint[] | { items?: ApiTimelinePoint[] }>(
    '/stats/timeline',
  );
  const items = Array.isArray(data) ? data : data.items || [];
  return items.map((item) => ({
    period: String(item.period || item.month || item.year || ''),
    count: item.count ?? item.value ?? 0,
  }));
}
