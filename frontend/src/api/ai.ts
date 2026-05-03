import { apiClient } from './client';
import type {
  AIModel,
  ClassifyBookRequest,
  ClassifyBookResponse,
  DetectDuplicateRequest,
  DetectDuplicateResponse,
  GenerateTagsRequest,
  GenerateTagsResponse,
  SummarizeBookRequest,
  SummarizeBookResponse,
} from '@/types/ai';

interface ApiAIModelsResponse {
  models: Array<{ name: string; size?: string; modified_at?: string }>;
}

interface ApiClassifyBookResponse {
  category_code: string;
  category_name: string;
  confidence: number;
  tags: string[];
  reason: string;
  model: string;
}

interface ApiGenerateTagsResponse {
  tags: string[];
  model: string;
}

interface ApiSummarizeBookResponse {
  summary: string;
  model: string;
}

interface ApiDetectDuplicateResponse {
  is_duplicate: boolean;
  confidence: number;
  reason: string;
  model: string;
}

export async function getAIModels(): Promise<AIModel[]> {
  const { data } = await apiClient.get<ApiAIModelsResponse>('/ai/models');
  return data.models.map((m) => ({
    name: m.name,
    size: m.size,
    modifiedAt: m.modified_at,
  }));
}

export async function classifyBook(req: ClassifyBookRequest): Promise<ClassifyBookResponse> {
  const { data } = await apiClient.post<ApiClassifyBookResponse>('/ai/classify-book', {
    title: req.title,
    author: req.author,
    publisher: req.publisher,
    summary: req.summary,
    model: req.model,
  });
  return {
    categoryCode: data.category_code,
    categoryName: data.category_name,
    confidence: data.confidence,
    tags: data.tags,
    reason: data.reason,
    model: data.model,
  };
}

export async function generateTags(req: GenerateTagsRequest): Promise<GenerateTagsResponse> {
  const { data } = await apiClient.post<ApiGenerateTagsResponse>('/ai/generate-tags', {
    title: req.title,
    author: req.author,
    publisher: req.publisher,
    summary: req.summary,
    model: req.model,
  });
  return { tags: data.tags, model: data.model };
}

export async function summarizeBook(req: SummarizeBookRequest): Promise<SummarizeBookResponse> {
  const { data } = await apiClient.post<ApiSummarizeBookResponse>('/ai/summarize-book', {
    title: req.title,
    author: req.author,
    publisher: req.publisher,
    summary: req.summary,
    model: req.model,
  });
  return { summary: data.summary, model: data.model };
}

export async function detectDuplicate(req: DetectDuplicateRequest): Promise<DetectDuplicateResponse> {
  const { data } = await apiClient.post<ApiDetectDuplicateResponse>('/ai/detect-duplicate', {
    book_a: req.bookA,
    book_b: req.bookB,
    model: req.model,
  });
  return {
    isDuplicate: data.is_duplicate,
    confidence: data.confidence,
    reason: data.reason,
    model: data.model,
  };
}
