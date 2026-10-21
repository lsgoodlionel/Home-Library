<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { fetchAIHealth, fetchAIProviderModels } from '@/api/ai';
import { AI_PROVIDER_LABELS } from '@/types/settings';
import type { AIHealthStatus } from '@/types/ai';
import type { AIProviderKey } from '@/types/settings';
import { getAIErrorMessage } from '@/utils/aiErrors';

const props = defineProps<{
  aiEnabled: boolean;
  provider: AIProviderKey;
  model: string;
}>();

const status = ref<AIHealthStatus | null>(null);
const models = ref<AIHealthStatus['models']>([]);
const safeError = ref('');
let requestSequence = 0;
let active = true;

const providerLabel = computed(() => AI_PROVIDER_LABELS[props.provider]);
const credentialLabel = computed(() => {
  if (status.value?.credentialState === 'configured') return '已配置';
  if (status.value?.credentialState === 'unusable') return '不可用';
  return '未配置';
});
const ollamaDetails = computed(() => props.provider === 'ollama' ? status.value?.details : undefined);

function formatCheckedAt(value: string | null | undefined): string {
  if (!value) return '尚未检查';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '尚未检查' : date.toLocaleString('zh-CN', { hour12: false });
}

async function refresh(provider: AIProviderKey): Promise<void> {
  const sequence = ++requestSequence;
  status.value = null;
  models.value = [];
  safeError.value = '';
  if (!props.aiEnabled) return;
  try {
    const [health, modelResult] = await Promise.all([
      fetchAIHealth(),
      fetchAIProviderModels(provider),
    ]);
    if (!active || sequence !== requestSequence || props.provider !== provider) return;
    status.value = health.provider === provider ? health : null;
    models.value = modelResult.provider === provider ? modelResult.models : [];
  } catch (error) {
    if (!active || sequence !== requestSequence || props.provider !== provider) return;
    safeError.value = getAIErrorMessage(error);
  }
}

watch(
  () => [props.aiEnabled, props.provider] as const,
  ([enabled, provider]) => {
    if (!enabled) {
      requestSequence += 1;
      status.value = null;
      models.value = [];
      safeError.value = '';
      return;
    }
    void refresh(provider);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  active = false;
  requestSequence += 1;
});
</script>

<template>
  <section class="current-ai-status" aria-label="当前 AI 运行状态">
    <div class="status-header">
      <div>
        <div class="status-title">当前 AI 运行状态</div>
        <div v-if="!aiEnabled" class="status-message">当前账号未启用 AI</div>
        <div v-else class="status-message">{{ safeError || status?.message || '正在检查' }}</div>
      </div>
      <el-tag>{{ aiEnabled ? (status?.status === 'available' ? '连接正常' : '尚未检查') : '已停用' }}</el-tag>
    </div>

    <el-alert v-if="safeError" type="error" :closable="false" :title="safeError" />

    <el-descriptions v-if="aiEnabled" :column="2" border class="status-details">
      <el-descriptions-item label="当前服务商">{{ providerLabel }}</el-descriptions-item>
      <el-descriptions-item label="当前模型">{{ status?.effectiveModel || model || '未配置' }}</el-descriptions-item>
      <el-descriptions-item label="有效地址">{{ status?.safeBaseUrl || '未配置' }}</el-descriptions-item>
      <el-descriptions-item label="凭据状态">{{ credentialLabel }}</el-descriptions-item>
      <el-descriptions-item label="最后检查">{{ formatCheckedAt(status?.checkedAt) }}</el-descriptions-item>
      <el-descriptions-item v-if="provider === 'ollama'" label="Ollama 版本">
        {{ ollamaDetails?.version || '-' }}
      </el-descriptions-item>
      <el-descriptions-item v-if="provider === 'ollama'" label="已安装模型">
        {{ ollamaDetails?.installedModelCount ?? 0 }}
      </el-descriptions-item>
      <el-descriptions-item v-if="provider === 'ollama'" label="正在运行模型">
        {{ ollamaDetails?.runningModelCount ?? 0 }}
      </el-descriptions-item>
      <el-descriptions-item v-if="provider === 'ollama'" label="当前使用 Access">
        {{ ollamaDetails?.usesAccess ? '是' : '否' }}
      </el-descriptions-item>
      <el-descriptions-item v-for="item in models" :key="`${item.provider}:${item.id}`" label="可用模型">
        {{ item.name }}
      </el-descriptions-item>
    </el-descriptions>
  </section>
</template>

<style scoped>
.current-ai-status {
  margin-bottom: 18px;
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}

.status-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.status-title { font-weight: 600; line-height: 1.4; }
.status-message { margin-top: 3px; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.5; }
.status-details { width: 100%; }
.status-details :deep(.el-descriptions__content) { overflow-wrap: anywhere; word-break: break-word; }

@media (max-width: 640px) {
  .status-header { align-items: stretch; flex-direction: column; }
}
</style>
