<script setup lang="ts">
import { ArrowDown, ArrowUp, RefreshLeft } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { computed, onMounted, reactive, ref } from 'vue';

import {
  DEFAULT_EXTERNAL_PROVIDER_ORDER,
  EXTERNAL_BOOK_PROVIDERS,
  fetchAvailableModels,
  loadLocalSettings,
  saveLocalSettings,
} from '@/api/settings';
import type { AIModel } from '@/types/ai';

const models = ref<AIModel[]>([]);
const loadingModels = ref(false);
const savingSettings = ref(false);

const settings = reactive(loadLocalSettings());
const orderedProviders = computed(() =>
  settings.externalProviderOrder
    .map((key) => EXTERNAL_BOOK_PROVIDERS.find((provider) => provider.key === key))
    .filter((provider): provider is (typeof EXTERNAL_BOOK_PROVIDERS)[number] => Boolean(provider)),
);

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

onMounted(loadModels);

function handleSave() {
  savingSettings.value = true;
  try {
    saveLocalSettings({
      ollamaBaseUrl: settings.ollamaBaseUrl,
      defaultModel: settings.defaultModel,
      externalSearchEnabled: settings.externalSearchEnabled,
      externalProviderOrder: [...settings.externalProviderOrder],
    });
    ElMessage.success('设置已保存（本地）');
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
      title="当前设置仅保存在本地浏览器，后端持久化接口尚未开放。刷新后仍可读取，清除浏览器数据后将重置为默认值。"
      class="info-alert"
    />

    <el-card class="settings-card">
      <template #header>
        <span>Ollama 配置</span>
      </template>

      <el-form label-width="140px">
        <el-form-item label="Ollama 地址">
          <el-input
            v-model="settings.ollamaBaseUrl"
            placeholder="http://localhost:11434"
            style="max-width: 400px"
          />
          <div class="field-hint">前端展示用，实际请求由后端转发。修改此处不影响后端配置。</div>
        </el-form-item>

        <el-form-item label="默认模型">
          <el-select
            v-model="settings.defaultModel"
            placeholder="选择默认模型"
            clearable
            style="max-width: 300px"
            :loading="loadingModels"
          >
            <el-option
              v-for="m in models"
              :key="m.name"
              :label="m.name"
              :value="m.name"
            />
          </el-select>
          <el-button
            :loading="loadingModels"
            style="margin-left: 8px"
            @click="handleRefreshModels"
          >
            刷新模型列表
          </el-button>
          <div class="field-hint">
            <template v-if="models.length === 0 && !loadingModels">
              未能获取模型列表，请确认 Ollama 已启动且后端可访问。
            </template>
            <template v-else-if="models.length > 0">
              共 {{ models.length }} 个可用模型。
            </template>
          </div>
        </el-form-item>
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
