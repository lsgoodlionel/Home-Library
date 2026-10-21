<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { Check, Connection, RefreshLeft } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';

import {
  fetchSystemAIConfig,
  resetSystemAIConfig,
  saveSystemAIConfig,
  testSystemAIConfig,
} from '@/api/settings';
import type { SystemAIConfig, SystemAIConfigUpdate } from '@/types/settings';
import { getAIErrorMessage } from '@/utils/aiErrors';

const emit = defineEmits<{
  'runtime-changed': [config: SystemAIConfig];
}>();

type AuthAction = 'save' | 'reset';

const config = ref<SystemAIConfig | null>(null);
const loading = ref(false);
const submitting = ref(false);
const testing = ref(false);
const authDialogVisible = ref(false);
const pendingAction = ref<AuthAction>('save');
const confirmInsecureTls = ref(false);
const clearAccessCredentials = ref(false);
const accessClientId = ref('');
const accessClientSecret = ref('');
const testStatus = ref('尚未测试');

const form = reactive({
  enabled: false,
  defaultBaseUrl: '',
  trustedBaseUrl: '',
  defaultModel: '',
  connectTimeoutSeconds: 20,
  readTimeoutSeconds: 180,
  verifyTls: true,
});

const auth = reactive({
  adminPassword: '',
  upgradePassword: '',
});

const sourceLabel = computed(() => {
  if (config.value?.configurationSource === 'database') return '数据库配置';
  if (config.value?.configurationSource === 'environment') return '环境变量';
  return '程序默认值';
});

const credentialLabel = computed(() => {
  const state = config.value?.credentialState;
  if (!state?.accessClientIdConfigured && !state?.accessClientSecretConfigured) return '未配置';
  if (state.credentialsUsable) return '凭据完整且可用';
  if (state.accessClientIdConfigured && state.accessClientSecretConfigured) return '已配置但不可用';
  return '凭据不完整';
});

const authTitle = computed(() => pendingAction.value === 'save' ? '保存服务器配置认证' : '恢复环境变量配置认证');
const authConfirmLabel = computed(() => pendingAction.value === 'save' ? '确认保存' : '确认恢复');

watch(clearAccessCredentials, (selected) => {
  if (selected) clearCredentialInputs();
});

function applyConfig(next: SystemAIConfig) {
  config.value = next;
  form.enabled = next.enabled;
  form.defaultBaseUrl = next.defaultBaseUrl;
  form.trustedBaseUrl = next.trustedBaseUrl;
  form.defaultModel = next.defaultModel;
  form.connectTimeoutSeconds = next.connectTimeoutSeconds;
  form.readTimeoutSeconds = next.readTimeoutSeconds;
  form.verifyTls = next.verifyTls;
}

function clearCredentialInputs() {
  accessClientId.value = '';
  accessClientSecret.value = '';
}

function clearSensitiveRefs() {
  auth.adminPassword = '';
  auth.upgradePassword = '';
  clearCredentialInputs();
  clearAccessCredentials.value = false;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const data = (error as {
      response?: { data?: { error?: { message?: string }; detail?: unknown; message?: string } };
    }).response?.data;
    if (typeof data?.error?.message === 'string' && data.error.message) return data.error.message;
    if (typeof data?.message === 'string' && data.message) return data.message;
    if (typeof data?.detail === 'string' && data.detail) return data.detail;
  }
  return fallback;
}

function validateForm(): boolean {
  if (!form.defaultBaseUrl.trim() || !form.trustedBaseUrl.trim() || !form.defaultModel.trim()) {
    ElMessage.warning('请完整填写服务器地址、可信地址和默认模型');
    return false;
  }
  if (form.connectTimeoutSeconds <= 0 || form.readTimeoutSeconds <= 0) {
    ElMessage.warning('超时时间必须大于 0');
    return false;
  }
  if (form.connectTimeoutSeconds >= form.readTimeoutSeconds) {
    ElMessage.warning('连接超时必须小于读取超时');
    return false;
  }
  const hasClientId = Boolean(accessClientId.value.trim());
  const hasClientSecret = Boolean(accessClientSecret.value.trim());
  if (!clearAccessCredentials.value && hasClientId !== hasClientSecret) {
    ElMessage.warning('必须同时填写完整的 Access Client ID 和 Client Secret');
    return false;
  }
  return true;
}

async function openSaveDialog() {
  if (!validateForm()) return;
  confirmInsecureTls.value = false;
  if (!form.verifyTls) {
    try {
      await ElMessageBox.confirm(
        '关闭 TLS 证书验证会降低连接安全性。仅在受控的自签名证书环境中继续。',
        'TLS 安全警告',
        {
          type: 'warning',
          confirmButtonText: '确认关闭验证',
          cancelButtonText: '取消',
        },
      );
      confirmInsecureTls.value = true;
    } catch {
      clearSensitiveRefs();
      confirmInsecureTls.value = false;
      return;
    }
  }
  pendingAction.value = 'save';
  authDialogVisible.value = true;
}

async function openResetDialog() {
  try {
    await ElMessageBox.confirm(
      '确认删除数据库中的服务器 AI 配置，并恢复环境变量或程序默认配置？',
      '恢复环境变量配置',
      {
        type: 'warning',
        confirmButtonText: '继续恢复',
        cancelButtonText: '取消',
      },
    );
  } catch {
    clearSensitiveRefs();
    confirmInsecureTls.value = false;
    return;
  }
  pendingAction.value = 'reset';
  authDialogVisible.value = true;
}

function cancelAuthDialog() {
  clearSensitiveRefs();
  confirmInsecureTls.value = false;
  authDialogVisible.value = false;
}

function handleAuthDialogVisibility(visible: boolean) {
  authDialogVisible.value = visible;
  if (!visible) {
    clearSensitiveRefs();
    confirmInsecureTls.value = false;
  }
}

function handleAuthDialogBeforeClose(done: () => void) {
  handleAuthDialogVisibility(false);
  done();
}

async function runFollowUpTest(operation: '保存' | '恢复') {
  try {
    const health = await testSystemAIConfig();
    testStatus.value = health.message;
  } catch (error) {
    const message = getAIErrorMessage(error);
    testStatus.value = message;
    ElMessage.warning(`配置已${operation}，但连接测试失败：${message}`);
  }
}

async function submitAuthenticatedAction() {
  if (!auth.adminPassword || !auth.upgradePassword) {
    ElMessage.warning('请输入当前管理员密码和服务器升级专用密码');
    return;
  }

  submitting.value = true;
  try {
    let next: SystemAIConfig;
    let operation: '保存' | '恢复';
    if (pendingAction.value === 'save') {
      const update: SystemAIConfigUpdate = {
        ...form,
        adminPassword: auth.adminPassword,
        upgradePassword: auth.upgradePassword,
        accessClientId: accessClientId.value.trim() || undefined,
        accessClientSecret: accessClientSecret.value.trim() || undefined,
        clearAccessCredentials: clearAccessCredentials.value,
        confirmInsecureTls: confirmInsecureTls.value,
      };
      next = await saveSystemAIConfig(update);
      operation = '保存';
    } else {
      next = await resetSystemAIConfig({
        adminPassword: auth.adminPassword,
        upgradePassword: auth.upgradePassword,
      });
      operation = '恢复';
    }

    applyConfig(next);
    clearSensitiveRefs();
    confirmInsecureTls.value = false;
    authDialogVisible.value = false;
    emit('runtime-changed', next);
    ElMessage.success(`服务器 AI 配置已${operation}`);
    await runFollowUpTest(operation);
  } catch (error) {
    ElMessage.error(getErrorMessage(error, pendingAction.value === 'save' ? '服务器 AI 配置保存失败' : '环境变量配置恢复失败'));
  } finally {
    clearSensitiveRefs();
    confirmInsecureTls.value = false;
    authDialogVisible.value = false;
    submitting.value = false;
  }
}

async function runConnectionTest() {
  testing.value = true;
  try {
    const health = await testSystemAIConfig();
    testStatus.value = health.message;
    ElMessage.success(health.message);
  } catch (error) {
    const message = getAIErrorMessage(error);
    testStatus.value = message;
    ElMessage.error(message);
  } finally {
    testing.value = false;
  }
}

async function loadConfig() {
  loading.value = true;
  try {
    applyConfig(await fetchSystemAIConfig());
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '服务器 AI 配置加载失败'));
  } finally {
    loading.value = false;
  }
}

onMounted(loadConfig);
</script>

<template>
  <section v-loading="loading" class="server-ai-settings" aria-label="服务器 AI 配置">
    <div class="section-heading">
      <div>
        <h3>服务器 AI 配置</h3>
        <p>全局运行参数与 Cloudflare Access 凭据状态</p>
      </div>
      <el-tag :type="config?.configurationSource === 'database' ? 'success' : 'info'">
        {{ sourceLabel }}
      </el-tag>
    </div>

    <el-descriptions :column="3" border class="runtime-summary">
      <el-descriptions-item label="服务器 AI">{{ config?.enabled ? '已启用' : '未启用' }}</el-descriptions-item>
      <el-descriptions-item label="TLS 验证">{{ config?.verifyTls ? '已启用' : '未启用' }}</el-descriptions-item>
      <el-descriptions-item label="Access 凭据">{{ credentialLabel }}</el-descriptions-item>
      <el-descriptions-item label="当前地址">{{ config?.defaultBaseUrl || '未配置' }}</el-descriptions-item>
      <el-descriptions-item label="默认模型">{{ config?.defaultModel || '未配置' }}</el-descriptions-item>
      <el-descriptions-item label="连接测试">{{ testStatus }}</el-descriptions-item>
    </el-descriptions>

    <el-alert
      v-if="config && !config.verifyTls"
      class="tls-alert"
      type="warning"
      :closable="false"
      show-icon
      title="TLS 证书验证已关闭，仅适用于受控环境"
    />

    <el-form label-position="top" class="settings-form">
      <div class="settings-grid">
        <el-form-item label="服务器 AI">
          <el-switch v-model="form.enabled" data-testid="enabled" active-text="启用" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="TLS 证书验证">
          <el-switch v-model="form.verifyTls" data-testid="verify-tls" active-text="启用" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="默认 Ollama 地址" class="wide-field">
          <el-input v-model="form.defaultBaseUrl" placeholder="https://ollama.example.com" />
        </el-form-item>
        <el-form-item label="Access 可信地址" class="wide-field">
          <el-input v-model="form.trustedBaseUrl" placeholder="https://ollama.example.com" />
        </el-form-item>
        <el-form-item label="默认模型">
          <el-input v-model="form.defaultModel" placeholder="qwen3.5:4b" />
        </el-form-item>
        <el-form-item label="连接超时（秒）">
          <el-input-number
            v-model="form.connectTimeoutSeconds"
            :min="1"
            :max="60"
            :precision="0"
            controls-position="right"
            class="number-input"
          />
        </el-form-item>
        <el-form-item label="读取超时（秒）">
          <el-input-number
            v-model="form.readTimeoutSeconds"
            :min="1"
            :max="299"
            :precision="0"
            controls-position="right"
            class="number-input"
          />
        </el-form-item>
        <el-form-item label="Access Client ID">
          <el-input
            v-model="accessClientId"
            data-testid="access-client-id"
            type="password"
            show-password
            autocomplete="new-password"
            :disabled="clearAccessCredentials"
            placeholder="留空则保留现有凭据"
          />
        </el-form-item>
        <el-form-item label="Access Client Secret">
          <el-input
            v-model="accessClientSecret"
            data-testid="access-client-secret"
            type="password"
            show-password
            autocomplete="new-password"
            :disabled="clearAccessCredentials"
            placeholder="留空则保留现有凭据"
          />
        </el-form-item>
      </div>

      <el-checkbox v-model="clearAccessCredentials" data-testid="clear-access-credentials">
        清除已保存的 Access 凭据
      </el-checkbox>

      <div class="settings-actions">
        <el-button type="primary" :icon="Check" :loading="submitting" @click="openSaveDialog">
          保存服务器配置
        </el-button>
        <el-button :icon="Connection" :loading="testing" @click="runConnectionTest">测试连接</el-button>
        <el-button type="warning" plain :icon="RefreshLeft" :loading="submitting" @click="openResetDialog">
          恢复环境变量配置
        </el-button>
      </div>
    </el-form>

    <el-dialog
      :model-value="authDialogVisible"
      @update:model-value="handleAuthDialogVisibility"
      :before-close="handleAuthDialogBeforeClose"
      data-testid="auth-dialog"
      :title="authTitle"
      width="min(480px, calc(100vw - 32px))"
      destroy-on-close
      :close-on-click-modal="false"
      @close="clearSensitiveRefs"
      @closed="clearSensitiveRefs"
    >
      <el-form label-position="top">
        <el-form-item label="当前管理员密码">
          <el-input
            v-model="auth.adminPassword"
            data-testid="admin-password"
            type="password"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-form-item label="服务器升级专用密码">
          <el-input
            v-model="auth.upgradePassword"
            data-testid="upgrade-password"
            type="password"
            show-password
            autocomplete="off"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="submitting" @click="cancelAuthDialog">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitAuthenticatedAction">
          {{ authConfirmLabel }}
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.server-ai-settings {
  min-height: 560px;
  padding: 16px 0;
}

.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.section-heading h3 {
  margin: 0;
  font-size: 18px;
  line-height: 1.4;
  letter-spacing: 0;
}

.section-heading p {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.runtime-summary,
.settings-form {
  width: 100%;
}

.runtime-summary :deep(.el-descriptions__content) {
  min-width: 120px;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.tls-alert {
  margin-top: 12px;
}

.settings-form {
  margin-top: 18px;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}

.wide-field {
  grid-column: 1 / -1;
}

.number-input {
  width: 100%;
}

.settings-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 20px;
  min-height: 32px;
}

.settings-actions :deep(.el-button) {
  min-width: 148px;
  min-height: 32px;
  height: auto;
  margin-left: 0;
  white-space: normal;
  line-height: 1.4;
}

@media (max-width: 720px) {
  .server-ai-settings {
    min-height: 640px;
  }

  .settings-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .wide-field {
    grid-column: auto;
  }

  .runtime-summary :deep(.el-descriptions__table),
  .runtime-summary :deep(tbody),
  .runtime-summary :deep(tr),
  .runtime-summary :deep(td) {
    display: block;
    width: 100%;
  }

  .settings-actions :deep(.el-button) {
    flex: 1 1 180px;
  }
}
</style>
