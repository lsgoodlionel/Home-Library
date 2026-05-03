import { apiClient, AUTH_TOKEN_STORAGE_KEY } from './client';

export { AUTH_TOKEN_STORAGE_KEY };

export type UserRole = 'admin' | 'member' | 'guest';
export type UserStatus = 'active' | 'disabled';

export interface ApiUser {
  id: number;
  username: string;
  display_name: string;
  email?: string;
  role: UserRole;
  status?: UserStatus;
}

export interface CurrentUser {
  id: number;
  username: string;
  displayName: string;
  email: string;
  role: UserRole;
  status: UserStatus;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: ApiUser;
}

export function normalizeUser(user: ApiUser): CurrentUser {
  return {
    id: user.id,
    username: user.username,
    displayName: user.display_name,
    email: user.email || '',
    role: user.role,
    status: user.status || 'active',
  };
}

export async function login(payload: LoginPayload) {
  const { data } = await apiClient.post<LoginResponse>('/auth/login', payload);
  return data;
}

export async function logout() {
  const { data } = await apiClient.post<{ ok: boolean }>('/auth/logout');
  return data;
}

export async function fetchMe() {
  const { data } = await apiClient.get<ApiUser>('/auth/me');
  return normalizeUser(data);
}
