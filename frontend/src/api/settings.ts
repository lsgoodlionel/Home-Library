import { getAIModels } from './ai';
import type { AIModel } from '@/types/ai';

export type { AIModel };

const SETTINGS_STORAGE_KEY = 'home_library_settings';

const defaults = {
  ollamaBaseUrl: 'http://localhost:11434',
  defaultModel: '',
  externalSearchEnabled: true,
};

export function loadLocalSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
    return raw ? { ...defaults, ...JSON.parse(raw) } : { ...defaults };
  } catch {
    return { ...defaults };
  }
}

export function saveLocalSettings(settings: typeof defaults) {
  localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
}

export async function fetchAvailableModels(): Promise<AIModel[]> {
  return getAIModels();
}
