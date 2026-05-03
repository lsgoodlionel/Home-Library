import {
  BOOK_STATUS_OPTIONS,
  READ_STATUS_OPTIONS,
  type BookStatus,
  type ReadStatus,
} from '@/types/book';

export const bookStatusLabel = Object.fromEntries(
  BOOK_STATUS_OPTIONS.map((item) => [item.value, item.label]),
) as Record<BookStatus, string>;

export const readStatusLabel = Object.fromEntries(
  READ_STATUS_OPTIONS.map((item) => [item.value, item.label]),
) as Record<ReadStatus, string>;

export const bookStatusTagType: Record<BookStatus, 'success' | 'warning' | 'info' | 'danger'> = {
  available: 'success',
  borrowed: 'warning',
  lost: 'danger',
  pending: 'info',
  gifted: 'info',
};

export const readStatusTagType: Record<ReadStatus, 'success' | 'warning' | 'info' | 'primary'> = {
  unread: 'info',
  reading: 'warning',
  read: 'success',
  paused: 'info',
};

export function getBookStatusLabel(status: BookStatus) {
  return bookStatusLabel[status];
}

export function getReadStatusLabel(status: ReadStatus) {
  return readStatusLabel[status];
}

export function getBookStatusTagType(status: BookStatus) {
  return bookStatusTagType[status];
}

export function getReadStatusTagType(status: ReadStatus) {
  return readStatusTagType[status];
}
