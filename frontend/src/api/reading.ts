import { apiClient } from './client';
import type { ReadingNote, ReadingNotePayload } from '@/types/reading';

interface ApiReadingNote {
  id: number;
  book_id: number;
  book?: {
    id: number;
    title: string;
    author?: string;
    cover_url?: string;
  } | null;
  user_id?: number | null;
  title: string;
  content?: string;
  progress?: number | null;
  rating?: number | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

function normalizeReadingNote(note: ApiReadingNote): ReadingNote {
  return {
    id: note.id,
    bookId: note.book_id,
    book: note.book
      ? {
          id: note.book.id,
          title: note.book.title,
          author: note.book.author || '',
          coverUrl: note.book.cover_url || '',
        }
      : null,
    userId: note.user_id ?? null,
    title: note.title,
    content: note.content || '',
    progress: note.progress ?? null,
    rating: note.rating ?? null,
    startedAt: note.started_at || null,
    finishedAt: note.finished_at || null,
    createdAt: note.created_at || '',
    updatedAt: note.updated_at || '',
  };
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function positiveNumberOrNull(value: number | null): number | null {
  return value !== null && value > 0 ? value : null;
}

function toNotePayload(payload: ReadingNotePayload) {
  return {
    title: payload.title.trim(),
    content: emptyToNull(payload.content),
    progress: payload.progress,
    rating: positiveNumberOrNull(payload.rating),
    started_at: payload.startedAt,
    finished_at: payload.finishedAt,
  };
}

export async function getBookNotes(bookId: number): Promise<ReadingNote[]> {
  const { data } = await apiClient.get<ApiReadingNote[]>(`/books/${bookId}/notes`);
  return data.map(normalizeReadingNote);
}

export async function createBookNote(bookId: number, payload: ReadingNotePayload): Promise<ReadingNote> {
  const { data } = await apiClient.post<ApiReadingNote>(`/books/${bookId}/notes`, toNotePayload(payload));
  return normalizeReadingNote(data);
}

export async function updateNote(id: number, payload: ReadingNotePayload): Promise<ReadingNote> {
  const { data } = await apiClient.patch<ApiReadingNote>(`/notes/${id}`, toNotePayload(payload));
  return normalizeReadingNote(data);
}

export async function deleteNote(id: number): Promise<void> {
  await apiClient.delete(`/notes/${id}`);
}
