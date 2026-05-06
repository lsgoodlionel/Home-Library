import { getAIModels } from './ai';
import type { AIModel } from '@/types/ai';
import type { AppSettings } from '@/types/settings';

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
