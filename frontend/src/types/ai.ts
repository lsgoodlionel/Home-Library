import type {
  AIProviderCredentialState,
  AIProviderKey,
  OllamaRuntimeStatus,
} from './settings';

export interface AIModel {
  name: string;
  size?: string;
  modifiedAt?: string;
}

export interface AIModelsResponse {
  models: AIModel[];
}

export interface AIProviderModel {
  provider: AIProviderKey;
  id: string;
  name: string;
}

export interface AIProviderDetails {
  version?: string;
  installedModelCount?: number;
  runningModelCount?: number;
  usesAccess?: boolean;
  [key: string]: unknown;
}

export type AIHealthState = 'unchecked' | 'available' | 'unavailable' | 'healthy' | 'error';

export interface AIHealthStatus {
  provider?: AIProviderKey;
  status: AIHealthState;
  message: string;
  checkedAt: string | null;
  effectiveModel?: string;
  safeBaseUrl?: string;
  credentialState?: AIProviderCredentialState;
  models?: AIProviderModel[];
  details?: AIProviderDetails;
  version?: string | null;
  installedModelCount?: number;
  runningModelCount?: number;
  generated?: boolean;
  ollamaRuntime?: OllamaRuntimeStatus | null;
}

export interface AIProviderDraft {
  provider?: AIProviderKey;
  baseUrl?: string;
  model?: string;
  apiKey?: string;
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

export interface BookContentFields {
  title?: string;
  subtitle?: string;
  author?: string;
  translator?: string;
  publisher?: string;
  publishYear?: number | null;
  isbn?: string;
  language?: string;
  pages?: number | null;
  coverUrl?: string;
  summary?: string;
  authorIntro?: string;
  binding?: string;
  series?: string;
  note?: string;
}

export interface BookContentCandidate extends BookContentFields {
  source: string;
  sourceId?: string;
  raw?: Record<string, unknown>;
}

export interface RecommendBookContentRequest {
  current: BookContentFields;
  candidates: BookContentCandidate[];
  missingFields: string[];
  model?: string;
}

export interface RecommendBookContentResponse {
  recommended: BookContentFields;
  sourceSummary: string;
  confidence: number;
  reason: string;
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
