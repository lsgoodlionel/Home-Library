export interface ApiLocation {
  id: number;
  room: string;
  shelf: string;
  layer: string;
  position: string;
  full_path: string;
  description: string;
  sort_order: number;
  created_at?: string;
  updated_at?: string;
}

export interface Location {
  id: number;
  room: string;
  shelf: string;
  layer: string;
  position: string;
  fullPath: string;
  description: string;
  sortOrder: number;
  createdAt?: string;
  updatedAt?: string;
}

export interface CreateLocationPayload {
  room: string;
  shelf: string;
  layer: string;
  position: string;
  description?: string;
  sort_order?: number;
}

export interface UpdateLocationPayload {
  room?: string;
  shelf?: string;
  layer?: string;
  position?: string;
  description?: string;
  sort_order?: number;
}

export interface LocationBrief {
  id: number;
  fullPath: string;
}

export function normalizeLocation(api: ApiLocation): Location {
  return {
    id: api.id,
    room: api.room,
    shelf: api.shelf,
    layer: api.layer,
    position: api.position,
    fullPath: api.full_path,
    description: api.description,
    sortOrder: api.sort_order,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}
