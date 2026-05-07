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
