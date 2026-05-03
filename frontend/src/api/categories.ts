import { apiClient } from './client';
import {
  normalizeCategory,
  type ApiCategory,
  type Category,
  type CreateCategoryPayload,
  type UpdateCategoryPayload,
} from '@/types/category';

export async function fetchCategories(): Promise<Category[]> {
  const { data } = await apiClient.get<ApiCategory[]>('/categories');
  return data.map(normalizeCategory);
}

export async function createCategory(payload: CreateCategoryPayload): Promise<Category> {
  const { data } = await apiClient.post<ApiCategory>('/categories', payload);
  return normalizeCategory(data);
}

export async function updateCategory(id: number, payload: UpdateCategoryPayload): Promise<Category> {
  const { data } = await apiClient.patch<ApiCategory>(`/categories/${id}`, payload);
  return normalizeCategory(data);
}

export async function deleteCategory(id: number): Promise<void> {
  await apiClient.delete(`/categories/${id}`);
}
