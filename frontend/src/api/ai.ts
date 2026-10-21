import { API_TIMEOUTS, apiClient } from './client';
import type {
  AIHealthStatus,
  AIModel,
  AIProviderDraft,
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
import type { AIProviderKey, OllamaRuntimeStatus } from '@/types/settings';

interface ApiAIModelsResponse {
  models: Array<{ name: string; size?: string; modified_at?: string }>;
}

interface ApiOllamaRuntimeStatus {
  enabled: boolean;
  base_url: string;
  default_model: string;
  connect_timeout_seconds: number;
  read_timeout_seconds: number;
  verify_tls: boolean;
  access_configured: boolean;
  uses_access: boolean;
}

interface ApiOllamaHealthResponse {
  status: AIHealthStatus['status'];
  message: string;
  checked_at?: string | null;
  version?: string | null;
  installed_model_count: number;
  running_model_count: number;
  generated: boolean;
  ollama_runtime?: ApiOllamaRuntimeStatus | null;
}

interface ApiAIProviderModel {
  provider: AIProviderKey;
  id: string;
  name: string;
}

interface ApiAIProviderHealthResponse {
  provider: AIProviderKey;
  status: 'available' | 'unavailable' | 'unchecked';
  message: string;
  checked_at?: string | null;
  effective_model: string;
  safe_base_url: string;
  credential_state: 'missing' | 'configured' | 'unusable';
  models: ApiAIProviderModel[];
  details: Record<string, unknown>;
}

function normalizeOllamaRuntime(data: ApiOllamaRuntimeStatus): OllamaRuntimeStatus {
  return {
    enabled: data.enabled,
    baseUrl: data.base_url,
    defaultModel: data.default_model,
    connectTimeoutSeconds: data.connect_timeout_seconds,
    readTimeoutSeconds: data.read_timeout_seconds,
    verifyTls: data.verify_tls,
    accessConfigured: data.access_configured,
    usesAccess: data.uses_access,
  };
}

function normalizeOllamaHealth(data: ApiOllamaHealthResponse): AIHealthStatus {
  return {
    status: data.status,
    message: data.message,
    checkedAt: data.checked_at || null,
    version: data.version || null,
    installedModelCount: data.installed_model_count,
    runningModelCount: data.running_model_count,
    generated: data.generated,
    ollamaRuntime: data.ollama_runtime ? normalizeOllamaRuntime(data.ollama_runtime) : null,
  };
}

function optionalNumber(value: unknown): number | undefined {
  return typeof value === 'number' ? value : undefined;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function normalizeProviderHealth(data: ApiAIProviderHealthResponse): AIHealthStatus {
  const details = data.details || {};
  return {
    provider: data.provider,
    status: data.status,
    message: data.message,
    checkedAt: data.checked_at || null,
    effectiveModel: data.effective_model,
    safeBaseUrl: data.safe_base_url,
    credentialState: data.credential_state,
    models: data.models.map((model) => ({ ...model })),
    details: {
      ...details,
      version: optionalString(details.version),
      installedModelCount: optionalNumber(details.installed_model_count),
      runningModelCount: optionalNumber(details.running_model_count),
      usesAccess: typeof details.uses_access === 'boolean' ? details.uses_access : undefined,
    },
  };
}

function providerDraftBody(draft?: AIProviderDraft): Record<string, string> {
  const body: Record<string, string> = {};
  if (!draft) return body;
  if (draft.provider) body.provider = draft.provider;
  if (draft.baseUrl) body.base_url = draft.baseUrl;
  if (draft.model) body.model = draft.model;
  if (draft.apiKey) body.api_key = draft.apiKey;
  return body;
}

async function runProviderOperation(
  provider: AIProviderKey,
  operation: 'test' | 'models' | 'generate-test',
  draft: AIProviderDraft | undefined,
): Promise<AIHealthStatus> {
  const { data } = await apiClient.post<ApiAIProviderHealthResponse>(
    `/ai/providers/${provider}/${operation}`,
    providerDraftBody(draft),
    { timeout: operation === 'generate-test' ? API_TIMEOUTS.aiGeneration : API_TIMEOUTS.aiHealth },
  );
  return normalizeProviderHealth(data);
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
  const { data } = await apiClient.get<ApiAIModelsResponse>('/ai/models', {
    timeout: API_TIMEOUTS.aiHealth,
  });
  return data.models.map((m) => ({
    name: m.name,
    size: m.size,
    modifiedAt: m.modified_at,
  }));
}

export async function fetchAIHealth(refresh = false): Promise<AIHealthStatus> {
  const { data } = await apiClient.get<ApiAIProviderHealthResponse>('/ai/health', {
    params: { refresh },
    timeout: API_TIMEOUTS.aiHealth,
  });
  return normalizeProviderHealth(data);
}

export function testAIProvider(provider: AIProviderKey, draft?: AIProviderDraft): Promise<AIHealthStatus> {
  return runProviderOperation(provider, 'test', draft);
}

export function fetchAIProviderModels(provider: AIProviderKey, draft?: AIProviderDraft): Promise<AIHealthStatus> {
  return runProviderOperation(provider, 'models', draft);
}

export function generateAIProviderTest(provider: AIProviderKey, draft?: AIProviderDraft): Promise<AIHealthStatus> {
  return runProviderOperation(provider, 'generate-test', draft);
}

export async function testAIConnection(generate: boolean): Promise<AIHealthStatus> {
  const { data } = await apiClient.post<ApiOllamaHealthResponse>(
    '/ai/test-connection',
    { generate },
    { timeout: generate ? API_TIMEOUTS.aiGeneration : API_TIMEOUTS.aiHealth },
  );
  return normalizeOllamaHealth(data);
}

export async function classifyBook(req: ClassifyBookRequest): Promise<ClassifyBookResponse> {
  const { data } = await apiClient.post<ApiClassifyBookResponse>('/ai/classify-book', {
    title: req.title,
    author: req.author,
    publisher: req.publisher,
    summary: req.summary,
    model: req.model,
  }, {
    timeout: API_TIMEOUTS.aiGeneration,
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
  }, {
    timeout: API_TIMEOUTS.aiGeneration,
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
  }, {
    timeout: API_TIMEOUTS.aiGeneration,
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
    raw_summary: req.summary,
    model: req.model,
  }, {
    timeout: API_TIMEOUTS.aiGeneration,
  });
  return { summary: data.summary, model: data.model };
}

export async function detectDuplicate(req: DetectDuplicateRequest): Promise<DetectDuplicateResponse> {
  const { data } = await apiClient.post<ApiDetectDuplicateResponse>('/ai/detect-duplicate', {
    first: req.bookA,
    second: req.bookB,
    model: req.model,
  }, {
    timeout: API_TIMEOUTS.aiGeneration,
  });
  return {
    isDuplicate: data.is_duplicate,
    confidence: data.confidence,
    reason: data.reason,
    model: data.model,
  };
}
