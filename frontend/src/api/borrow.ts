import { apiClient } from './client';
import type { BorrowCreatePayload, BorrowRecord, BorrowReturnPayload } from '@/types/borrow';

interface ApiBorrowRecord {
  id: number;
  book_id: number;
  book?: {
    id: number;
    title: string;
    author?: string;
    cover_url?: string;
  } | null;
  borrower_name: string;
  borrower_contact?: string;
  borrowed_at: string;
  due_at?: string | null;
  returned_at?: string | null;
  status: BorrowRecord['status'];
  note?: string;
  created_at?: string;
  updated_at?: string;
}

function normalizeBorrowRecord(record: ApiBorrowRecord): BorrowRecord {
  return {
    id: record.id,
    bookId: record.book_id,
    book: record.book
      ? {
          id: record.book.id,
          title: record.book.title,
          author: record.book.author || '',
          coverUrl: record.book.cover_url || '',
        }
      : null,
    borrowerName: record.borrower_name,
    borrowerContact: record.borrower_contact || '',
    borrowedAt: record.borrowed_at,
    dueAt: record.due_at || null,
    returnedAt: record.returned_at || null,
    status: record.status,
    note: record.note || '',
    createdAt: record.created_at || '',
    updatedAt: record.updated_at || '',
  };
}

function toBorrowPayload(payload: BorrowCreatePayload) {
  return {
    book_id: payload.bookId,
    borrower_name: payload.borrowerName,
    borrower_contact: payload.borrowerContact,
    borrowed_at: payload.borrowedAt,
    due_at: payload.dueAt,
    note: payload.note,
  };
}

export async function createBorrow(payload: BorrowCreatePayload): Promise<BorrowRecord> {
  const { data } = await apiClient.post<ApiBorrowRecord>('/borrow', toBorrowPayload(payload));
  return normalizeBorrowRecord(data);
}

export async function returnBorrow(id: number, payload: BorrowReturnPayload): Promise<BorrowRecord> {
  const { data } = await apiClient.post<ApiBorrowRecord>(`/borrow/${id}/return`, {
    returned_at: payload.returnedAt,
    note: payload.note,
  });
  return normalizeBorrowRecord(data);
}

export async function getBorrowRecords(): Promise<BorrowRecord[]> {
  const { data } = await apiClient.get<ApiBorrowRecord[]>('/borrow/records');
  return data.map(normalizeBorrowRecord);
}

export async function getActiveBorrows(): Promise<BorrowRecord[]> {
  const { data } = await apiClient.get<ApiBorrowRecord[]>('/borrow/active');
  return data.map(normalizeBorrowRecord);
}
