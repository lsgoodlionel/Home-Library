<script setup lang="ts">
import { ArrowDown, ArrowUp, RefreshLeft } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { computed, onMounted, reactive, ref } from 'vue';

import {
  DEFAULT_EXTERNAL_PROVIDER_ORDER,
  EXTERNAL_BOOK_PROVIDERS,
  fetchAIModelSettings,
  fetchAvailableModels,
  loadLocalSettings,
  saveAIModelSettings,
  saveLocalSettings,
} from '@/api/settings';
import type { AIModel } from '@/types/ai';
import type { AIModelSettings, AIProviderConfig, AIProviderKey } from '@/types/settings';

const models = ref<AIModel[]>([]);
const loadingModels = ref(false);
const savingSettings = ref(false);
const loadingAISettings = ref(false);

const settings = reactive(loadLocalSettings());
const aiSettings = reactive<AIModelSettings>({
  activeProvider: 'ollama',
  defaultModel: '',
  providers: [],
});
const orderedProviders = computed(() =>
  settings.externalProviderOrder
    .map((key) => EXTERNAL_BOOK_PROVIDERS.find((provider) => provider.key === key))
    .filter((provider): provider is (typeof EXTERNAL_BOOK_PROVIDERS)[number] => Boolean(provider)),
);
const activeAIProvider = computed(() =>
  aiSettings.providers.find((provider) => provider.provider === aiSettings.activeProvider),
);
const aiProviderLabels: Record<AIProviderKey, string> = {
  ollama: 'Ollama',
  openai: 'OpenAI',
  gemini: 'Google Gemini',
  deepseek: 'DeepSeek',
  moonshot: 'Kimi / Moonshot',
  qwen: '通义千问',
  custom: '自定义兼容接口',
};

async function loadModels() {
  loadingModels.value = true;
  try {
    models.value = await fetchAvailableModels();
  } catch {
    models.value = [];
  } finally {
    loadingModels.value = false;
  }
}

async function loadAISettings() {
  loadingAISettings.value = true;
  try {
    const data = await fetchAIModelSettings();
    applyAISettings(data);
  } catch {
    ElMessage.error('AI 模型配置加载失败');
  } finally {
    loadingAISettings.value = false;
  }
}

onMounted(async () => {
  await loadAISettings();
  await loadModels();
});

function applyAISettings(data: AIModelSettings) {
  aiSettings.activeProvider = data.activeProvider;
  aiSettings.defaultModel = data.defaultModel;
  aiSettings.providers = data.providers.map((provider) => ({ ...provider, apiKey: '' }));
}

async function handleSave() {
  savingSettings.value = true;
  try {
    const savedAI = await saveAIModelSettings({
      activeProvider: aiSettings.activeProvider,
      defaultModel: aiSettings.defaultModel,
      providers: aiSettings.providers,
    });
    applyAISettings(savedAI);
    saveLocalSettings({
      ollamaBaseUrl: getProvider('ollama')?.baseUrl || settings.ollamaBaseUrl,
      defaultModel: aiSettings.defaultModel,
      externalSearchEnabled: settings.externalSearchEnabled,
      externalProviderOrder: [...settings.externalProviderOrder],
    });
    ElMessage.success('设置已保存到当前账号');
    await loadModels();
  } catch {
    ElMessage.error('设置保存失败');
  } finally {
    savingSettings.value = false;
  }
}

function handleRefreshModels() {
  loadModels();
}

function moveProvider(index: number, direction: -1 | 1) {
  const targetIndex = index + direction;
  if (targetIndex < 0 || targetIndex >= settings.externalProviderOrder.length) {
    return;
  }
  const nextOrder = [...settings.externalProviderOrder];
  const [item] = nextOrder.splice(index, 1);
  nextOrder.splice(targetIndex, 0, item);
  settings.externalProviderOrder = nextOrder;
}

function resetProviderOrder() {
  settings.externalProviderOrder = [...DEFAULT_EXTERNAL_PROVIDER_ORDER];
}

function getProvider(provider: AIProviderKey): AIProviderConfig | undefined {
  return aiSettings.providers.find((item) => item.provider === provider);
}

function handleProviderChange(provider: AIProviderKey) {
  const selected = getProvider(provider);
  if (selected?.defaultModel) {
    aiSettings.defaultModel = selected.defaultModel;
  }
}
</script>

<template>
  <div class="settings-page">
    <div class="page-header">
      <h2 class="page-title">系统设置</h2>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="AI 模型配置已按当前登录账号保存到后端；外部检索顺序暂保留浏览器本地设置。"
      class="info-alert"
    />

    <el-card class="settings-card">
      <template #header>
        <span>AI 模型配置</span>
      </template>

      <el-form v-loading="loadingAISettings" label-width="140px">
        <el-form-item label="当前服务商">
          <el-select
            v-model="aiSettings.activeProvider"
            style="max-width: 320px"
            @change="handleProviderChange"
          >
            <el-option
              v-for="provider in aiSettings.providers"
              :key="provider.provider"
              :label="aiProviderLabels[provider.provider]"
              :value="provider.provider"
            />
          </el-select>
          <div class="field-hint">
            当前仅 Ollama 接入实际调用；其他服务商先保存接口地址、API Key 与默认模型，后续接入调用层。
          </div>
        </el-form-item>

        <el-form-item label="默认模型">
          <el-input v-model="aiSettings.defaultModel" placeholder="如 qwen2.5" style="max-width: 320px" />
          <el-button
            v-if="aiSettings.activeProvider === 'ollama'"
            :loading="loadingModels"
            style="margin-left: 8px"
            @click="handleRefreshModels"
          >
            刷新模型列表
          </el-button>
          <div class="field-hint">
            <template v-if="models.length === 0 && !loadingModels">
              未能获取模型列表，请确认当前 Ollama 地址可由后端访问。
            </template>
            <template v-else-if="models.length > 0">
              共 {{ models.length }} 个可用模型。
            </template>
          </div>
        </el-form-item>

        <el-divider />

        <div class="provider-config-list">
          <div
            v-for="provider in aiSettings.providers"
            :key="provider.provider"
            class="ai-provider-panel"
          >
            <div class="provider-panel-header">
              <div>
                <div class="provider-name">{{ aiProviderLabels[provider.provider] }}</div>
                <div class="provider-desc">{{ provider.note }}</div>
              </div>
              <el-switch
                v-model="provider.enabled"
                active-text="启用"
                inactive-text="停用"
                :disabled="provider.provider === 'ollama'"
              />
            </div>

            <el-form-item :label="provider.provider === 'ollama' ? 'Ollama 地址' : 'API 地址'">
              <el-input
                v-model="provider.baseUrl"
                :placeholder="provider.provider === 'ollama' ? 'http://localhost:11434 或远程 Ollama 地址' : 'https://...'"
              />
            </el-form-item>
            <el-form-item v-if="provider.provider !== 'ollama'" label="API Key">
              <el-input
                v-model="provider.apiKey"
                show-password
                placeholder="留空表示保持已保存的 Key"
              />
              <div v-if="provider.hasApiKey" class="field-hint">当前账号已有已保存 Key；输入新值会覆盖。</div>
            </el-form-item>
            <el-form-item label="服务商默认模型">
              <el-input v-model="provider.defaultModel" placeholder="例如 qwen2.5、gpt-4.1-mini、gemini-2.5-flash" />
            </el-form-item>
          </div>
        </div>
      </el-form>
    </el-card>

    <el-card class="settings-card">
      <template #header>
        <span>外部检索</span>
      </template>

      <el-form label-width="140px">
        <el-form-item label="外部书源检索">
          <el-switch
            v-model="settings.externalSearchEnabled"
            active-text="开启"
            inactive-text="关闭"
          />
          <div class="field-hint">开启后可通过 ISBN / 书名从下列外部数据源检索图书信息。</div>
        </el-form-item>

        <el-form-item label="默认检索顺序">
          <div class="provider-order">
            <div
              v-for="(provider, index) in orderedProviders"
              :key="provider.key"
              class="provider-row"
            >
              <div class="provider-rank">{{ index + 1 }}</div>
              <div class="provider-info">
                <div class="provider-name">{{ provider.name }}</div>
                <div class="provider-desc">{{ provider.description }}</div>
              </div>
              <div class="provider-actions">
                <el-tooltip content="上移" placement="top">
                  <el-button
                    :icon="ArrowUp"
                    circle
                    size="small"
                    :disabled="index === 0"
                    @click="moveProvider(index, -1)"
                  />
                </el-tooltip>
                <el-tooltip content="下移" placement="top">
                  <el-button
                    :icon="ArrowDown"
                    circle
                    size="small"
                    :disabled="index === orderedProviders.length - 1"
                    @click="moveProvider(index, 1)"
                  />
                </el-tooltip>
              </div>
            </div>
          </div>
          <el-button
            class="reset-order-button"
            :icon="RefreshLeft"
            @click="resetProviderOrder"
          >
            恢复默认顺序
          </el-button>
          <div class="field-hint">智能入库和 ISBN 检索会按此顺序调用并排序；需要 API Key 的数据源在未配置时不会返回结果。</div>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="settings-card">
      <template #header>
        <span>备份设置</span>
      </template>

      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="备份功能正在开发中，当前版本暂不支持自动备份配置。可通过导出功能手动导出图书数据。"
      />

      <el-form label-width="140px" style="margin-top: 16px">
        <el-form-item label="手动导出">
          <el-button disabled>导出全部图书数据（开发中）</el-button>
        </el-form-item>
        <el-form-item label="自动备份">
          <el-switch disabled />
          <div class="field-hint">自动备份功能暂未开放。</div>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="save-bar">
      <el-button type="primary" :loading="savingSettings" @click="handleSave">
        保存设置
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  padding: 0;
  max-width: 800px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.info-alert {
  margin-bottom: 16px;
}

.settings-card {
  margin-bottom: 16px;
}

.field-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-color-info);
  line-height: 1.4;
}

.provider-order {
  width: 100%;
  max-width: 560px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  overflow: hidden;
}

.provider-row {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--el-fill-color-blank);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.provider-row:last-child {
  border-bottom: 0;
}

.provider-rank {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  font-weight: 600;
}

.provider-info {
  min-width: 0;
}

.provider-name {
  font-weight: 600;
  line-height: 1.4;
}

.provider-desc {
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.provider-config-list {
  display: grid;
  gap: 12px;
}

.ai-provider-panel {
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}

.provider-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.provider-actions {
  display: flex;
  gap: 8px;
}

.reset-order-button {
  margin-top: 10px;
}

.save-bar {
  padding: 8px 0;
}
</style>
