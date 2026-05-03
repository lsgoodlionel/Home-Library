export type UserRole = 'admin' | 'member' | 'guest';
export type UserStatus = 'active' | 'disabled';

export interface User {
  id: number;
  username: string;
  displayName: string;
  email: string;
  role: UserRole;
  status: UserStatus;
}

export interface CreateUserPayload {
  username: string;
  password: string;
  display_name: string;
  email: string;
  role: UserRole;
  status: UserStatus;
}

export interface UpdateUserPayload {
  display_name?: string;
  email?: string;
  role?: UserRole;
  status?: UserStatus;
}

export interface UserListParams {
  page?: number;
  page_size?: number;
  keyword?: string;
  role?: UserRole | '';
  status?: UserStatus | '';
}
