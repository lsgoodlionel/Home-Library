export interface AppSettings {
  ollamaBaseUrl: string;
  defaultModel: string;
  externalSearchEnabled: boolean;
  externalProviderOrder: string[];
}

export type AIProviderKey = 'ollama' | 'openai' | 'gemini' | 'deepseek' | 'moonshot' | 'qwen' | 'custom';

export interface AIProviderConfig {
  provider: AIProviderKey;
  enabled: boolean;
  baseUrl: string;
  apiKey: string;
  defaultModel: string;
  note: string;
  hasApiKey: boolean;
}

export interface AIModelSettings {
  activeProvider: AIProviderKey;
  defaultModel: string;
  providers: AIProviderConfig[];
}

export type ExternalSearchProviderKey = 'google_books' | 'isbn_work' | 'douban';

export interface ExternalSearchProviderConfig {
  provider: ExternalSearchProviderKey;
  enabled: boolean;
  apiKey: string;
  extra: string;
  note: string;
  hasApiKey: boolean;
  hasExtra: boolean;
}

export interface ExternalSearchSettings {
  providers: ExternalSearchProviderConfig[];
}

export interface ExternalProviderValidationResult {
  provider: ExternalSearchProviderKey;
  ok: boolean;
  message: string;
}

export interface AppVersionInfo {
  appName: string;
  version: string;
  environment: string;
}

export type UpgradeStatus = 'pending' | 'running' | 'success' | 'failed';

export interface UpgradeStartResult {
  taskId: string;
  status: UpgradeStatus;
  message: string;
}

export interface UpgradeTaskStatus {
  taskId: string;
  status: UpgradeStatus;
  startedAt: string;
  finishedAt: string;
  exitCode: number | null;
  output: string;
  error: string;
}
