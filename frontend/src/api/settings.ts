import { getAIModels } from './ai';
import { API_TIMEOUTS, apiClient } from './client';
import type { AIHealthStatus, AIModel } from '@/types/ai';
import type {
  AIModelSettings,
  AIProviderConfig,
  AIProviderKey,
  AppVersionInfo,
  AppSettings,
  ExternalProviderValidationResult,
  ExternalSearchProviderConfig,
  ExternalSearchProviderKey,
  ExternalSearchSettings,
  OllamaRuntimeStatus,
  SystemAIAuth,
  SystemAIConfig,
  SystemAIConfigUpdate,
  SystemAIConfigurationSource,
  UpgradeStartResult,
  UpgradeTaskStatus,
} from '@/types/settings';

export type { AIModel };

const SETTINGS_STORAGE_KEY = 'home_library_settings';

export const EXTERNAL_BOOK_PROVIDERS = [
  {
    key: 'nlc',
    name: 'NLC（国家图书馆）',
    description: '国家图书馆馆藏目录，中文书目权威，通常不提供封面。',
  },
  {
    key: 'isbn_work',
    name: 'ISBN Work',
    description: '中文 ISBN 元数据源；需要后端配置 ISBN_WORK_API_KEY 后才会返回结果。',
  },
  {
    key: 'douban',
    name: '豆瓣读书',
    description: '中文书名、作者和封面补全效果较好。',
  },
  {
    key: 'google_books',
    name: 'Google Books',
    description: '覆盖面广，适合外文图书和 ISBN 元数据补全。',
  },
  {
    key: 'open_library',
    name: 'Open Library',
    description: '开放图书数据源，适合作为英文书目兜底检索。',
  },
] as const;

export const DEFAULT_EXTERNAL_PROVIDER_ORDER = EXTERNAL_BOOK_PROVIDERS.map((provider) => provider.key);

const defaults: AppSettings = {
  ollamaBaseUrl: 'http://localhost:11434',
  defaultModel: '',
  externalSearchEnabled: true,
  externalProviderOrder: DEFAULT_EXTERNAL_PROVIDER_ORDER,
};

function normalizeProviderOrder(value: unknown): string[] {
  const savedOrder = Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
  const validKeys = new Set<string>(DEFAULT_EXTERNAL_PROVIDER_ORDER);
  const ordered = savedOrder.filter((key) => validKeys.has(key));
  const missing = DEFAULT_EXTERNAL_PROVIDER_ORDER.filter((key) => !ordered.includes(key));
  return [...ordered, ...missing];
}

export function loadLocalSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) {
      return { ...defaults };
    }
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    return {
      ...defaults,
      ...parsed,
      externalProviderOrder: normalizeProviderOrder(parsed.externalProviderOrder),
    };
  } catch {
    return { ...defaults };
  }
}

export function saveLocalSettings(settings: AppSettings) {
  localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
}

export async function fetchAvailableModels(): Promise<AIModel[]> {
  return getAIModels();
}

export async function fetchSystemAIModels(): Promise<AIModel[]> {
  const { data } = await apiClient.get<{
    models: Array<{ name: string; size?: string; modified_at?: string }>;
  }>('/system/ai-config/models', {
    timeout: API_TIMEOUTS.aiHealth,
  });
  return data.models.map((model) => ({
    name: model.name,
    size: model.size,
    modifiedAt: model.modified_at,
  }));
}

interface ApiAIProviderConfig {
  provider: AIProviderKey;
  enabled: boolean;
  base_url: string;
  default_model: string;
  note: string;
  has_api_key: boolean;
  credential_state: AIProviderConfig['credentialState'];
}

interface ApiAISettingsResponse {
  ai_enabled: boolean;
  active_provider: AIProviderKey;
  default_model: string;
  providers: ApiAIProviderConfig[];
  ollama_runtime: ApiOllamaRuntimeStatus;
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

interface ApiSystemAICredentialState {
  access_client_id_configured: boolean;
  access_client_secret_configured: boolean;
  credentials_usable: boolean;
  source: SystemAIConfigurationSource;
}

interface ApiSystemAIConfigResponse {
  enabled: boolean;
  default_base_url: string;
  trusted_base_url: string;
  default_model: string;
  connect_timeout_seconds: number;
  read_timeout_seconds: number;
  verify_tls: boolean;
  credential_state: ApiSystemAICredentialState;
  configuration_source: SystemAIConfigurationSource;
  config_version: number;
}

interface ApiAIHealthResponse {
  status: AIHealthStatus['status'];
  message: string;
  checked_at?: string | null;
  version?: string | null;
  installed_model_count: number;
  running_model_count: number;
  generated: boolean;
  ollama_runtime?: ApiOllamaRuntimeStatus | null;
}

interface ApiExternalSearchProviderConfig {
  provider: ExternalSearchProviderKey;
  enabled: boolean;
  api_key: string;
  extra: string;
  note: string;
  has_api_key: boolean;
  has_extra: boolean;
}

interface ApiExternalSearchSettingsResponse {
  providers: ApiExternalSearchProviderConfig[];
}

interface ApiVersionResponse {
  app_name?: string;
  version?: string;
  environment?: string;
}

interface ApiUpgradeStartResponse {
  task_id: string;
  status: UpgradeStartResult['status'];
  message: string;
}

interface ApiUpgradeStatusResponse {
  task_id: string;
  status: UpgradeTaskStatus['status'];
  started_at: string;
  finished_at?: string | null;
  exit_code?: number | null;
  output?: string;
  error?: string;
}

function normalizeAIProvider(config: ApiAIProviderConfig): AIProviderConfig {
  return {
    provider: config.provider,
    enabled: config.enabled,
    baseUrl: config.base_url,
    defaultModel: config.default_model,
    note: config.note,
    credentialState: config.credential_state,
  };
}

function normalizeOllamaRuntime(config: ApiOllamaRuntimeStatus): OllamaRuntimeStatus {
  return {
    enabled: config.enabled,
    baseUrl: config.base_url,
    defaultModel: config.default_model,
    connectTimeoutSeconds: config.connect_timeout_seconds,
    readTimeoutSeconds: config.read_timeout_seconds,
    verifyTls: config.verify_tls,
    accessConfigured: config.access_configured,
    usesAccess: config.uses_access,
  };
}

function normalizeSystemAIConfig(data: ApiSystemAIConfigResponse): SystemAIConfig {
  return {
    enabled: data.enabled,
    defaultBaseUrl: data.default_base_url,
    trustedBaseUrl: data.trusted_base_url,
    defaultModel: data.default_model,
    connectTimeoutSeconds: data.connect_timeout_seconds,
    readTimeoutSeconds: data.read_timeout_seconds,
    verifyTls: data.verify_tls,
    credentialState: {
      accessClientIdConfigured: data.credential_state.access_client_id_configured,
      accessClientSecretConfigured: data.credential_state.access_client_secret_configured,
      credentialsUsable: data.credential_state.credentials_usable,
      source: data.credential_state.source,
    },
    configurationSource: data.configuration_source,
    configVersion: data.config_version,
  };
}

function normalizeSystemAIHealth(data: ApiAIHealthResponse): AIHealthStatus {
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

export async function fetchSystemAIConfig(): Promise<SystemAIConfig> {
  const { data } = await apiClient.get<ApiSystemAIConfigResponse>('/system/ai-config');
  return normalizeSystemAIConfig(data);
}

export async function saveSystemAIConfig(input: SystemAIConfigUpdate): Promise<SystemAIConfig> {
  const body: Record<string, unknown> = {
    enabled: input.enabled,
    default_base_url: input.defaultBaseUrl,
    trusted_base_url: input.trustedBaseUrl,
    default_model: input.defaultModel,
    connect_timeout_seconds: input.connectTimeoutSeconds,
    read_timeout_seconds: input.readTimeoutSeconds,
    verify_tls: input.verifyTls,
    admin_password: input.adminPassword,
    upgrade_password: input.upgradePassword,
    clear_access_credentials: input.clearAccessCredentials,
    confirm_insecure_tls: input.confirmInsecureTls,
  };
  if (input.accessClientId) {
    body.access_client_id = input.accessClientId;
  }
  if (input.accessClientSecret) {
    body.access_client_secret = input.accessClientSecret;
  }
  const { data } = await apiClient.put<ApiSystemAIConfigResponse>('/system/ai-config', body);
  return normalizeSystemAIConfig(data);
}

export async function resetSystemAIConfig(auth: SystemAIAuth): Promise<SystemAIConfig> {
  const { data } = await apiClient.delete<ApiSystemAIConfigResponse>('/system/ai-config', {
    data: {
      admin_password: auth.adminPassword,
      upgrade_password: auth.upgradePassword,
      confirm_reset: true,
    },
  });
  return normalizeSystemAIConfig(data);
}

export async function testSystemAIConfig(): Promise<AIHealthStatus> {
  const { data } = await apiClient.post<ApiAIHealthResponse>(
    '/system/ai-config/test',
    {},
    { timeout: API_TIMEOUTS.aiHealth },
  );
  return normalizeSystemAIHealth(data);
}

function normalizeAISettings(data: ApiAISettingsResponse): AIModelSettings {
  return {
    aiEnabled: data.ai_enabled,
    activeProvider: data.active_provider,
    defaultModel: data.default_model,
    providers: data.providers.map(normalizeAIProvider),
    ollamaRuntime: normalizeOllamaRuntime(data.ollama_runtime),
  };
}

export async function fetchAIModelSettings(): Promise<AIModelSettings> {
  const { data } = await apiClient.get<ApiAISettingsResponse>('/ai/config');
  return normalizeAISettings(data);
}

export async function saveAIModelSettings(settings: AIModelSettings): Promise<AIModelSettings> {
  const providers = settings.providers.map((provider) => {
    const payload: Record<string, unknown> = {
      provider: provider.provider,
      enabled: provider.enabled,
      base_url: provider.baseUrl,
      default_model: provider.defaultModel,
      note: provider.note,
      clear_api_key: provider.clearApiKey === true,
    };
    if (provider.apiKey) payload.api_key = provider.apiKey;
    return payload;
  });
  const { data } = await apiClient.put<ApiAISettingsResponse>('/ai/config', {
    ai_enabled: settings.aiEnabled,
    active_provider: settings.activeProvider,
    default_model: settings.defaultModel,
    providers,
  });
  return normalizeAISettings(data);
}

function normalizeExternalProvider(config: ApiExternalSearchProviderConfig): ExternalSearchProviderConfig {
  return {
    provider: config.provider,
    enabled: config.enabled,
    apiKey: config.api_key,
    extra: config.extra,
    note: config.note,
    hasApiKey: config.has_api_key,
    hasExtra: config.has_extra,
  };
}

function normalizeExternalSettings(data: ApiExternalSearchSettingsResponse): ExternalSearchSettings {
  return {
    providers: data.providers.map(normalizeExternalProvider),
  };
}

export async function fetchExternalSearchSettings(): Promise<ExternalSearchSettings> {
  const { data } = await apiClient.get<ApiExternalSearchSettingsResponse>('/search/config');
  return normalizeExternalSettings(data);
}

export async function fetchAppVersion(): Promise<AppVersionInfo> {
  const { data } = await apiClient.get<ApiVersionResponse>('/version');
  return {
    appName: data.app_name || 'Home Library',
    version: data.version || 'unknown',
    environment: data.environment || 'unknown',
  };
}

export async function startServerUpgrade(upgradePassword: string): Promise<UpgradeStartResult> {
  const { data } = await apiClient.post<ApiUpgradeStartResponse>('/upgrade', {
    upgrade_password: upgradePassword,
  });
  return {
    taskId: data.task_id,
    status: data.status,
    message: data.message,
  };
}

export async function fetchUpgradeStatus(taskId: string): Promise<UpgradeTaskStatus> {
  const { data } = await apiClient.get<ApiUpgradeStatusResponse>(`/upgrade/${taskId}`);
  return {
    taskId: data.task_id,
    status: data.status,
    startedAt: data.started_at,
    finishedAt: data.finished_at || '',
    exitCode: data.exit_code ?? null,
    output: data.output || '',
    error: data.error || '',
  };
}

export async function saveExternalSearchSettings(settings: ExternalSearchSettings): Promise<ExternalSearchSettings> {
  const { data } = await apiClient.put<ApiExternalSearchSettingsResponse>('/search/config', {
    providers: settings.providers.map((provider) => ({
      provider: provider.provider,
      enabled: provider.enabled,
      api_key: provider.apiKey,
      extra: provider.extra,
      note: provider.note,
    })),
  });
  return normalizeExternalSettings(data);
}

export async function validateExternalProvider(
  provider: ExternalSearchProviderConfig,
): Promise<ExternalProviderValidationResult> {
  const { data } = await apiClient.post<ExternalProviderValidationResult>(`/search/providers/${provider.provider}/validate`, {
    provider: provider.provider,
    enabled: provider.enabled,
    api_key: provider.apiKey,
    extra: provider.extra,
    note: provider.note,
  });
  return data;
}
