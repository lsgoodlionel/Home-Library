<script setup lang="ts">
import { Connection, Promotion, Refresh } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';

import { fetchAIProviderModels, generateAIProviderTest, testAIProvider } from '@/api/ai';
import { fetchAIModelSettings, saveAIModelSettings } from '@/api/settings';
import type { AIProviderDraft, AIProviderHealthStatus, AIProviderModel } from '@/types/ai';
import { AI_PROVIDER_LABELS } from '@/types/settings';
import type { AIModelSettings, AIProviderConfig, AIProviderKey, OllamaRuntimeStatus } from '@/types/settings';
import { getAIErrorMessage } from '@/utils/aiErrors';

const emit = defineEmits<{ saved: [settings: AIModelSettings] }>();

interface ProviderDraftState extends AIProviderConfig {
  apiKey: string;
  clearApiKey: boolean;
  models: AIProviderModel[];
  result: string;
  loading: '' | 'test' | 'models' | 'generate';
}

const emptyRuntime: OllamaRuntimeStatus = {
  enabled: false,
  baseUrl: '',
  defaultModel: '',
  connectTimeoutSeconds: 0,
  readTimeoutSeconds: 0,
  verifyTls: true,
  accessConfigured: false,
  usesAccess: false,
};
const loading = ref(false);
const saving = ref(false);
const aiEnabled = ref(true);
const activeProvider = ref<AIProviderKey>('ollama');
const ollamaRuntime = ref<OllamaRuntimeStatus>({ ...emptyRuntime });
const providers = reactive<ProviderDraftState[]>([]);
const requestSequences = new Map<AIProviderKey, number>();
const generationLocks = new Set<AIProviderKey>();
let mounted = true;

const validActiveProviders = computed(() => providers.filter((provider) => {
  if (!provider.enabled || !provider.baseUrl.trim() || !provider.defaultModel.trim()) return false;
  return provider.provider === 'ollama'
    || Boolean(provider.apiKey.trim())
    || (provider.hasApiKey && provider.credentialState === 'configured' && !provider.clearApiKey);
}));

function replaceProviders(settings: AIModelSettings): void {
  providers.splice(0, providers.length, ...settings.providers.map((provider) => ({
    ...provider,
    apiKey: '',
    clearApiKey: false,
    models: [],
    result: '',
    loading: '' as const,
  })));
  aiEnabled.value = settings.aiEnabled;
  activeProvider.value = settings.activeProvider;
  ollamaRuntime.value = { ...settings.ollamaRuntime };
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    replaceProviders(await fetchAIModelSettings());
  } catch {
    ElMessage.error('账号 AI 配置加载失败');
  } finally {
    loading.value = false;
  }
}

function operationDraft(provider: ProviderDraftState): AIProviderDraft {
  return {
    provider: provider.provider,
    baseUrl: provider.baseUrl.trim(),
    model: provider.defaultModel.trim(),
    apiKey: provider.apiKey || undefined,
  };
}

function nextSequence(provider: AIProviderKey): number {
  const next = (requestSequences.get(provider) || 0) + 1;
  requestSequences.set(provider, next);
  return next;
}

function operationSnapshot(provider: ProviderDraftState): string {
  return JSON.stringify([
    provider.enabled,
    provider.baseUrl,
    provider.apiKey,
    provider.defaultModel,
    provider.clearApiKey,
  ]);
}

function invalidateProvider(provider: ProviderDraftState): void {
  nextSequence(provider.provider);
  provider.loading = '';
  provider.result = '';
  provider.models = [];
}

async function runOperation(provider: ProviderDraftState, operation: 'test' | 'models' | 'generate'): Promise<void> {
  if (!mounted || !aiEnabled.value || !provider.enabled) return;
  const sequence = nextSequence(provider.provider);
  const snapshot = `${aiEnabled.value}:${operationSnapshot(provider)}`;
  provider.loading = operation;
  try {
    const draft = operationDraft(provider);
    const result: AIProviderHealthStatus = operation === 'test'
      ? await testAIProvider(provider.provider, draft)
      : operation === 'models'
        ? await fetchAIProviderModels(provider.provider, draft)
        : await generateAIProviderTest(provider.provider, draft);
    if (
      !mounted
      || requestSequences.get(provider.provider) !== sequence
      || result.provider !== provider.provider
      || snapshot !== `${aiEnabled.value}:${operationSnapshot(provider)}`
    ) return;
    provider.result = result.message;
    if (operation === 'models') provider.models = result.models.map((model) => ({ ...model }));
    ElMessage.success(operation === 'models' ? '模型列表已刷新' : operation === 'generate' ? '生成测试成功' : '连接测试成功');
  } catch (error) {
    if (!mounted || requestSequences.get(provider.provider) !== sequence) return;
    provider.result = getAIErrorMessage(error);
    ElMessage.error(provider.result);
  } finally {
    if (mounted && requestSequences.get(provider.provider) === sequence) provider.loading = '';
  }
}

async function confirmGenerate(provider: ProviderDraftState): Promise<void> {
  if (!mounted || !aiEnabled.value || !provider.enabled || generationLocks.has(provider.provider)) return;
  const snapshot = operationSnapshot(provider);
  const sequence = requestSequences.get(provider.provider) || 0;
  generationLocks.add(provider.provider);
  provider.loading = 'generate';
  try {
    await ElMessageBox.confirm(
      '生成测试会调用当前服务商执行一次最小生成，可能产生费用或消耗账号额度。确认继续吗？',
      '确认生成测试',
      { type: 'warning', confirmButtonText: '继续生成测试', cancelButtonText: '取消' },
    );
    if (!mounted || !aiEnabled.value || !provider.enabled
      || (requestSequences.get(provider.provider) || 0) !== sequence
      || operationSnapshot(provider) !== snapshot) return;
    await runOperation(provider, 'generate');
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('生成测试确认失败');
  } finally {
    generationLocks.delete(provider.provider);
    if (provider.loading === 'generate') provider.loading = '';
  }
}

function savePayload(): AIModelSettings {
  const active = providers.find((provider) => provider.provider === activeProvider.value);
  return {
    aiEnabled: aiEnabled.value,
    activeProvider: activeProvider.value,
    defaultModel: active?.defaultModel || '',
    providers: providers.map(({ models: _models, result: _result, loading: _loading, ...provider }) => ({ ...provider })),
    ollamaRuntime: { ...ollamaRuntime.value },
  };
}

async function save(): Promise<void> {
  if (aiEnabled.value && !validActiveProviders.value.some((provider) => provider.provider === activeProvider.value)) {
    ElMessage.warning('请先选择已启用且配置有效的当前服务商');
    return;
  }
  saving.value = true;
  try {
    const saved = await saveAIModelSettings(savePayload());
    replaceProviders(saved);
    emit('saved', saved);
    ElMessage.success('当前账号 AI 配置已保存');
  } catch {
    ElMessage.error('当前账号 AI 配置保存失败');
  } finally {
    saving.value = false;
  }
}

function credentialLabel(provider: ProviderDraftState): string {
  if (provider.clearApiKey) return '保存后清除';
  if (provider.apiKey) return '将替换已保存 Key';
  if (provider.credentialState === 'configured') return '已配置（留空保持）';
  if (provider.credentialState === 'unusable') return '已保存但不可用，请重新录入';
  return '未配置';
}

onMounted(() => void load());
watch(aiEnabled, () => {
  providers.forEach(invalidateProvider);
}, { flush: 'sync' });
watch(
  () => providers.map(operationSnapshot),
  (current, previous = []) => {
    current.forEach((snapshot, index) => {
      if (snapshot !== previous[index] && providers[index]) invalidateProvider(providers[index]);
    });
  },
  { flush: 'sync' },
);
onBeforeUnmount(() => {
  mounted = false;
  generationLocks.clear();
  providers.forEach((provider) => nextSequence(provider.provider));
});
</script>

<template>
  <section v-loading="loading" class="account-ai-settings" aria-label="当前账号 AI 配置">
    <h3 class="section-title">当前账号 AI 配置</h3>
    <el-form label-position="top">
      <div class="account-controls">
        <el-form-item label="账号 AI">
          <el-switch v-model="aiEnabled" data-testid="account-ai-enabled" active-text="启用" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="当前服务商">
          <el-select v-model="activeProvider" data-testid="active-provider" :disabled="!aiEnabled" placeholder="选择已启用且配置有效的服务商">
            <el-option v-for="provider in validActiveProviders" :key="provider.provider" :label="AI_PROVIDER_LABELS[provider.provider]" :value="provider.provider" />
          </el-select>
        </el-form-item>
      </div>

      <div class="provider-list">
        <section v-for="provider in providers" :key="provider.provider" class="provider-panel" :data-provider="provider.provider">
          <div class="provider-header">
            <div>
              <div class="provider-name">{{ AI_PROVIDER_LABELS[provider.provider] }}</div>
              <div v-if="provider.note" class="field-hint">{{ provider.note }}</div>
            </div>
            <el-switch v-model="provider.enabled" data-testid="provider-enabled" active-text="启用" inactive-text="停用" :disabled="aiEnabled && activeProvider === provider.provider" />
          </div>
          <div class="provider-fields">
            <el-form-item :label="provider.provider === 'ollama' ? 'Ollama 地址' : 'API 地址'">
              <el-input v-model="provider.baseUrl" data-testid="provider-address" />
            </el-form-item>
            <el-form-item v-if="provider.provider !== 'ollama'" label="API Key">
              <el-input v-model="provider.apiKey" data-testid="provider-api-key" type="password" show-password :disabled="provider.clearApiKey" placeholder="留空保持已保存 Key" />
              <div class="field-hint">{{ credentialLabel(provider) }}</div>
              <el-checkbox v-model="provider.clearApiKey" data-testid="clear-api-key">显式清除已保存 Key</el-checkbox>
            </el-form-item>
            <el-form-item label="服务商默认模型">
              <el-select v-model="provider.defaultModel" data-testid="provider-model" allow-create clearable filterable placeholder="选择或输入模型名">
                <el-option v-for="model in provider.models" :key="`${provider.provider}:${model.id}`" :label="model.name" :value="model.id" />
              </el-select>
            </el-form-item>
          </div>
          <div class="provider-actions">
            <el-button :icon="Connection" :disabled="!aiEnabled || !provider.enabled" :loading="provider.loading === 'test'" @click="runOperation(provider, 'test')">测试连接</el-button>
            <el-button :icon="Refresh" :disabled="!aiEnabled || !provider.enabled" :loading="provider.loading === 'models'" @click="runOperation(provider, 'models')">刷新模型</el-button>
            <el-button type="warning" plain :icon="Promotion" :disabled="!aiEnabled || !provider.enabled" :loading="provider.loading === 'generate'" @click="confirmGenerate(provider)">生成测试</el-button>
          </div>
          <el-alert v-if="provider.result" class="operation-result" :closable="false" :title="provider.result" />
        </section>
      </div>
      <div class="save-actions"><el-button type="primary" :loading="saving" @click="save">保存账号 AI 配置</el-button></div>
    </el-form>
  </section>
</template>

<style scoped>
.account-ai-settings { width: 100%; }
.section-title { margin: 0 0 16px; font-size: 18px; letter-spacing: 0; }
.account-controls { display: grid; grid-template-columns: minmax(160px, 220px) minmax(240px, 1fr); gap: 16px; }
.provider-list { display: grid; gap: 16px; }
.provider-panel { padding: 16px 0; border-top: 1px solid var(--el-border-color-lighter); }
.provider-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.provider-name { font-weight: 600; line-height: 1.5; }
.provider-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }
.provider-fields :deep(.el-form-item) { min-width: 0; }
.provider-fields :deep(.el-select) { width: 100%; }
.field-hint { margin-top: 4px; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.5; }
.provider-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.provider-actions :deep(.el-button) { margin-left: 0; }
.operation-result { margin-top: 12px; }
.save-actions { display: flex; justify-content: flex-end; margin-top: 18px; }
@media (max-width: 640px) {
  .account-controls, .provider-fields { grid-template-columns: 1fr; gap: 0; }
  .provider-actions :deep(.el-button) { flex: 1 1 120px; }
}
</style>
