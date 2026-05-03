export interface AIModel {
  name: string;
  size?: string;
  modifiedAt?: string;
}

export interface AIModelsResponse {
  models: AIModel[];
}

export interface ClassifyBookRequest {
  title: string;
  author?: string;
  publisher?: string;
  summary?: string;
  model?: string;
}

export interface ClassifyBookResponse {
  categoryCode: string;
  categoryName: string;
  confidence: number;
  tags: string[];
  reason: string;
  model: string;
}

export interface GenerateTagsRequest {
  title: string;
  author?: string;
  publisher?: string;
  summary?: string;
  model?: string;
}

export interface GenerateTagsResponse {
  tags: string[];
  model: string;
}

export interface SummarizeBookRequest {
  title: string;
  author?: string;
  publisher?: string;
  summary?: string;
  model?: string;
}

export interface SummarizeBookResponse {
  summary: string;
  model: string;
}

export interface DetectDuplicateRequest {
  bookA: Record<string, unknown>;
  bookB: Record<string, unknown>;
  model?: string;
}

export interface DetectDuplicateResponse {
  isDuplicate: boolean;
  confidence: number;
  reason: string;
  model: string;
}

export type AIStatus = 'idle' | 'loading' | 'success' | 'error' | 'unavailable';
