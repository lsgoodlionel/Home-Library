import { apiClient } from './client';
import type {
  AIModel,
  ClassifyBookRequest,
  ClassifyBookResponse,
  DetectDuplicateRequest,
  DetectDuplicateResponse,
  GenerateTagsRequest,
  GenerateTagsResponse,
  RecommendBookContentRequest,
  RecommendBookContentResponse,
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

interface ApiBookContentFields {
  title?: string | null;
  subtitle?: string | null;
  author?: string | null;
  translator?: string | null;
  publisher?: string | null;
  publish_year?: number | null;
  isbn?: string | null;
  language?: string | null;
  pages?: number | null;
  cover_url?: string | null;
  summary?: string | null;
  author_intro?: string | null;
  binding?: string | null;
  series?: string | null;
  note?: string | null;
}

interface ApiBookContentCandidate extends ApiBookContentFields {
  source: string;
  source_id?: string | null;
  raw?: Record<string, unknown>;
}

interface ApiRecommendBookContentResponse {
  recommended: ApiBookContentFields;
  source_summary: string;
  confidence: number;
  reason: string;
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

function toApiBookContentFields(fields: RecommendBookContentRequest['current']): ApiBookContentFields {
  return {
    title: fields.title,
    subtitle: fields.subtitle,
    author: fields.author,
    translator: fields.translator,
    publisher: fields.publisher,
    publish_year: fields.publishYear,
    isbn: fields.isbn,
    language: fields.language,
    pages: fields.pages,
    cover_url: fields.coverUrl,
    summary: fields.summary,
    author_intro: fields.authorIntro,
    binding: fields.binding,
    series: fields.series,
    note: fields.note,
  };
}

function fromApiBookContentFields(fields: ApiBookContentFields): RecommendBookContentResponse['recommended'] {
  return {
    title: fields.title || undefined,
    subtitle: fields.subtitle || undefined,
    author: fields.author || undefined,
    translator: fields.translator || undefined,
    publisher: fields.publisher || undefined,
    publishYear: fields.publish_year ?? null,
    isbn: fields.isbn || undefined,
    language: fields.language || undefined,
    pages: fields.pages ?? null,
    coverUrl: fields.cover_url || undefined,
    summary: fields.summary || undefined,
    authorIntro: fields.author_intro || undefined,
    binding: fields.binding || undefined,
    series: fields.series || undefined,
    note: fields.note || undefined,
  };
}

export async function recommendBookContent(
  req: RecommendBookContentRequest,
): Promise<RecommendBookContentResponse> {
  const candidates: ApiBookContentCandidate[] = req.candidates.map((candidate) => ({
    ...toApiBookContentFields(candidate),
    source: candidate.source,
    source_id: candidate.sourceId,
    raw: candidate.raw,
  }));
  const { data } = await apiClient.post<ApiRecommendBookContentResponse>('/ai/recommend-book-content', {
    current: toApiBookContentFields(req.current),
    candidates,
    missing_fields: req.missingFields,
    model: req.model,
  });
  return {
    recommended: fromApiBookContentFields(data.recommended),
    sourceSummary: data.source_summary,
    confidence: data.confidence,
    reason: data.reason,
    model: data.model,
  };
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
