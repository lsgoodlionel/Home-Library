import type { BookListItem } from './book';

export type BorrowStatus = 'active' | 'returned' | 'overdue';

export interface BorrowRecord {
  id: number;
  bookId: number;
  book?: Pick<BookListItem, 'id' | 'title' | 'author' | 'coverUrl'> | null;
  borrowerName: string;
  borrowerContact: string;
  borrowedAt: string;
  dueAt: string | null;
  returnedAt: string | null;
  status: BorrowStatus;
  note: string;
  createdAt: string;
  updatedAt: string;
}

export interface BorrowCreatePayload {
  bookId: number;
  borrowerName: string;
  borrowerContact: string;
  borrowedAt: string;
  dueAt: string | null;
  note: string;
}

export interface BorrowReturnPayload {
  returnedAt: string;
  note: string;
}

export function isBorrowOverdue(record: BorrowRecord) {
  if (record.returnedAt || !record.dueAt) {
    return false;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return new Date(record.dueAt).getTime() < today.getTime();
}

export function createEmptyBorrowPayload(bookId = 0): BorrowCreatePayload {
  const today = new Date().toISOString().slice(0, 10);
  return {
    bookId,
    borrowerName: '',
    borrowerContact: '',
    borrowedAt: today,
    dueAt: null,
    note: '',
  };
}
