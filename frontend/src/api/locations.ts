import { apiClient } from './client';
import {
  normalizeLocation,
  type ApiLocation,
  type CreateLocationPayload,
  type Location,
  type UpdateLocationPayload,
} from '@/types/location';

export async function fetchLocations(): Promise<Location[]> {
  const { data } = await apiClient.get<ApiLocation[]>('/locations');
  return data.map(normalizeLocation);
}

export async function createLocation(payload: CreateLocationPayload): Promise<Location> {
  const { data } = await apiClient.post<ApiLocation>('/locations', payload);
  return normalizeLocation(data);
}

export async function updateLocation(id: number, payload: UpdateLocationPayload): Promise<Location> {
  const { data } = await apiClient.patch<ApiLocation>(`/locations/${id}`, payload);
  return normalizeLocation(data);
}

export async function deleteLocation(id: number): Promise<void> {
  await apiClient.delete(`/locations/${id}`);
}
