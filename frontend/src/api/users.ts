import { apiClient } from './client';
import type { CreateUserPayload, UpdateUserPayload, User, UserListParams } from '@/types/user';

interface ApiUser {
  id: number;
  username: string;
  display_name: string;
  email?: string;
  role: User['role'];
  status: User['status'];
}

interface ApiUserListResponse {
  items: ApiUser[];
  total: number;
  page: number;
  page_size: number;
}

export interface UserListResult {
  items: User[];
  total: number;
  page: number;
  pageSize: number;
}

function normalizeUser(u: ApiUser): User {
  return {
    id: u.id,
    username: u.username,
    displayName: u.display_name,
    email: u.email || '',
    role: u.role,
    status: u.status,
  };
}

export async function fetchUsers(params?: UserListParams): Promise<UserListResult> {
  const { data } = await apiClient.get<ApiUserListResponse>('/users', { params });
  return {
    items: data.items.map(normalizeUser),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
  };
}

export async function createUser(payload: CreateUserPayload): Promise<User> {
  const { data } = await apiClient.post<ApiUser>('/users', payload);
  return normalizeUser(data);
}

export async function updateUser(id: number, payload: UpdateUserPayload): Promise<User> {
  const body: Record<string, unknown> = {};
  if (payload.display_name !== undefined) body.display_name = payload.display_name;
  if (payload.email !== undefined) body.email = payload.email;
  if (payload.role !== undefined) body.role = payload.role;
  if (payload.status !== undefined) body.status = payload.status;
  const { data } = await apiClient.patch<ApiUser>(`/users/${id}`, body);
  return normalizeUser(data);
}

export async function deleteUser(id: number): Promise<void> {
  await apiClient.delete(`/users/${id}`);
}
