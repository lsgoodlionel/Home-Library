export interface ApiCategory {
  id: number;
  code: string;
  name: string;
  parent_id: number | null;
  description: string;
  sort_order: number;
  is_system: boolean;
  children: ApiCategory[];
  created_at?: string;
  updated_at?: string;
}

export interface Category {
  id: number;
  code: string;
  name: string;
  parentId: number | null;
  description: string;
  sortOrder: number;
  isSystem: boolean;
  children: Category[];
  createdAt?: string;
  updatedAt?: string;
}

export interface CreateCategoryPayload {
  code: string;
  name: string;
  parent_id?: number | null;
  description?: string;
  sort_order?: number;
}

export interface UpdateCategoryPayload {
  code?: string;
  name?: string;
  description?: string;
  sort_order?: number;
}

export interface CategoryBrief {
  id: number;
  code: string;
  name: string;
}

export function normalizeCategory(api: ApiCategory): Category {
  return {
    id: api.id,
    code: api.code,
    name: api.name,
    parentId: api.parent_id,
    description: api.description,
    sortOrder: api.sort_order,
    isSystem: api.is_system,
    children: api.children.map(normalizeCategory),
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}
