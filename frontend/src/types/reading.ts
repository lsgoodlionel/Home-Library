import type { BookListItem } from './book';

export interface ReadingNote {
  id: number;
  bookId: number;
  book?: Pick<BookListItem, 'id' | 'title' | 'author' | 'coverUrl'> | null;
  userId?: number | null;
  title: string;
  content: string;
  progress: number | null;
  rating: number | null;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ReadingNotePayload {
  title: string;
  content: string;
  progress: number | null;
  rating: number | null;
  startedAt: string | null;
  finishedAt: string | null;
}

export function createEmptyReadingNotePayload(): ReadingNotePayload {
  return {
    title: '',
    content: '',
    progress: null,
    rating: null,
    startedAt: null,
    finishedAt: null,
  };
}
