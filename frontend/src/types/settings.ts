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

export interface OllamaRuntimeStatus {
  enabled: boolean;
  baseUrl: string;
  defaultModel: string;
  connectTimeoutSeconds: number;
  readTimeoutSeconds: number;
  verifyTls: boolean;
  accessConfigured: boolean;
  usesAccess: boolean;
}

export type SystemAIConfigurationSource = 'database' | 'environment' | 'default';

export interface SystemAICredentialState {
  accessClientIdConfigured: boolean;
  accessClientSecretConfigured: boolean;
  credentialsUsable: boolean;
  source: SystemAIConfigurationSource;
}

export interface SystemAIConfig {
  enabled: boolean;
  defaultBaseUrl: string;
  trustedBaseUrl: string;
  defaultModel: string;
  connectTimeoutSeconds: number;
  readTimeoutSeconds: number;
  verifyTls: boolean;
  credentialState: SystemAICredentialState;
  configurationSource: SystemAIConfigurationSource;
  configVersion: number;
}

export interface SystemAIAuth {
  adminPassword: string;
  upgradePassword: string;
}

export interface SystemAIConfigUpdate extends SystemAIAuth {
  enabled: boolean;
  defaultBaseUrl: string;
  trustedBaseUrl: string;
  defaultModel: string;
  connectTimeoutSeconds: number;
  readTimeoutSeconds: number;
  verifyTls: boolean;
  accessClientId?: string;
  accessClientSecret?: string;
  clearAccessCredentials: boolean;
  confirmInsecureTls: boolean;
}

export interface AIModelSettings {
  activeProvider: AIProviderKey;
  defaultModel: string;
  providers: AIProviderConfig[];
  ollamaRuntime: OllamaRuntimeStatus;
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
