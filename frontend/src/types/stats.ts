export interface StatBookSummary {
  id: number;
  title: string;
  author: string;
  categoryName: string;
  locationPath: string;
  createdAt: string;
}

export interface ActiveBorrowSummary {
  id: number;
  bookId: number;
  bookTitle: string;
  borrowerName: string;
  borrowedAt: string;
  dueAt: string;
}

export interface StatsOverview {
  totalBooks: number;
  availableBooks: number;
  borrowedBooks: number;
  readBooks: number;
  unreadBooks: number;
  favoriteBooks: number;
  recentBooks: StatBookSummary[];
  activeBorrows: ActiveBorrowSummary[];
}

export interface DistributionItem {
  id?: number;
  name: string;
  count: number;
  code?: string;
}

export interface ReadingStats {
  unread: number;
  reading: number;
  read: number;
  paused: number;
}

export interface TimelinePoint {
  period: string;
  count: number;
}

export interface AuthorRankItem {
  name: string;
  count: number;
}
