<script setup lang="ts">
import { ArrowDown, ArrowUp, RefreshLeft } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, onMounted, reactive, ref } from 'vue';

import { classifyBook } from '@/api/ai';
import { bookDetailToForm, getBook, getBooks, getCategoryOptions, updateBook } from '@/api/books';
import {
  DEFAULT_EXTERNAL_PROVIDER_ORDER,
  EXTERNAL_BOOK_PROVIDERS,
  fetchAIModelSettings,
  fetchAvailableModels,
  loadLocalSettings,
  saveAIModelSettings,
  saveLocalSettings,
} from '@/api/settings';
import {
  confirmBooksImport,
  downloadBooksExport,
  downloadImportTemplate,
  previewBooksImport,
  type BackupFormat,
  type ImportPreviewResult,
} from '@/api/importExport';
import type { AIModel, ClassifyBookResponse } from '@/types/ai';
import type { BookListItem, CategoryOption } from '@/types/book';
import type { AIModelSettings, AIProviderConfig, AIProviderKey } from '@/types/settings';

const models = ref<AIModel[]>([]);
const loadingModels = ref(false);
const savingSettings = ref(false);
const loadingAISettings = ref(false);
const backupFormat = ref<BackupFormat>('xlsx');
const backupFile = ref<File | null>(null);
const importPreview = ref<ImportPreviewResult | null>(null);
const importing = ref(false);
const exporting = ref(false);
const downloadingTemplate = ref(false);
const autoClassifying = ref(false);
const stopAutoClassifyRequested = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);

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
const modelOptions = computed(() => {
  const names = models.value.map((model) => model.name).filter(Boolean);
  if (aiSettings.defaultModel && !names.includes(aiSettings.defaultModel)) {
    names.unshift(aiSettings.defaultModel);
  }
  return names;
});
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
    if (!aiSettings.defaultModel && models.value.length > 0) {
      setDefaultModel(models.value[0].name);
    }
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
    setDefaultModel(selected.defaultModel);
  }
}

function setDefaultModel(model: string) {
  aiSettings.defaultModel = model;
  const provider = getProvider(aiSettings.activeProvider);
  if (provider) {
    provider.defaultModel = model;
  }
}

async function handleDownloadTemplate() {
  downloadingTemplate.value = true;
  try {
    await downloadImportTemplate(backupFormat.value);
    ElMessage.success('已下载导入模板');
  } catch (err: unknown) {
    ElMessage.error(`模板下载失败：${getErrorMessage(err)}`);
  } finally {
    downloadingTemplate.value = false;
  }
}

async function handleExportBooks() {
  exporting.value = true;
  try {
    await downloadBooksExport(backupFormat.value);
    ElMessage.success('已导出全部图书数据');
  } catch (err: unknown) {
    ElMessage.error(`导出失败：${getErrorMessage(err)}`);
  } finally {
    exporting.value = false;
  }
}

function openImportPicker() {
  fileInputRef.value?.click();
}

async function handleImportFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0] || null;
  input.value = '';
  if (!file) return;
  backupFile.value = file;
  importing.value = true;
  try {
    importPreview.value = await previewBooksImport(file, backupFormat.value);
    if (importPreview.value.invalidRows > 0) {
      ElMessage.warning(`预览完成：${importPreview.value.invalidRows} 行存在错误，修正后再导入`);
    } else {
      ElMessage.success(`预览完成：${importPreview.value.validRows} 行可导入`);
    }
  } catch (err: unknown) {
    importPreview.value = null;
    backupFile.value = null;
    ElMessage.error(`导入预览失败：${getErrorMessage(err)}`);
  } finally {
    importing.value = false;
  }
}

async function handleConfirmImport() {
  if (!backupFile.value || !importPreview.value) {
    ElMessage.warning('请先选择文件并完成预览');
    return;
  }
  if (importPreview.value.invalidRows > 0) {
    ElMessage.warning('导入文件仍有错误，请修正后重新预览');
    return;
  }
  importing.value = true;
  try {
    const result = await confirmBooksImport(backupFile.value, backupFormat.value);
    ElMessage.success(`导入完成：新增 ${result.importedCount} 本图书`);
    backupFile.value = null;
    importPreview.value = null;
  } catch (err: unknown) {
    ElMessage.error(`导入失败：${getErrorMessage(err)}`);
  } finally {
    importing.value = false;
  }
}

async function handleAutoClassifyUncategorized() {
  autoClassifying.value = true;
  stopAutoClassifyRequested.value = false;
  try {
    const [books, categories] = await Promise.all([fetchUncategorizedBooks(), getCategoryOptions()]);
    if (books.length === 0) {
      ElMessage.success('当前没有未分类图书');
      return;
    }

    await ElMessageBox.confirm(
      `找到 ${books.length} 本未分类图书。系统会逐本调用 AI 分类推荐，每本都需要确认后才会写入分类和标签。`,
      '一键分类确认',
      { type: 'warning', confirmButtonText: '开始处理', cancelButtonText: '取消' },
    );

    let updatedCount = 0;
    let skippedCount = 0;
    for (const book of books) {
      if (stopAutoClassifyRequested.value) break;
      const result = await classifyBook({
        title: book.title,
        author: book.author,
        publisher: book.publisher,
        model: aiSettings.defaultModel || undefined,
      });
      if (stopAutoClassifyRequested.value) break;
      const category = resolveCategoryRecommendation(categories, result.categoryCode, result.categoryName);
      const accepted = await confirmClassifyBook(book, result, category);
      if (stopAutoClassifyRequested.value) break;
      if (!accepted || !category) {
        skippedCount += 1;
        continue;
      }

      const detail = await getBook(book.id);
      if (stopAutoClassifyRequested.value) break;
      const form = bookDetailToForm(detail);
      form.categoryId = category.id;
      form.tagNames = Array.from(new Set([...form.tagNames, ...result.tags]));
      await updateBook(book.id, form);
      updatedCount += 1;
      ElMessage.success(`已分类：${book.title} -> ${category.code} ${category.name}`);
    }
    if (stopAutoClassifyRequested.value) {
      ElMessage.warning(`一键分类已停止，已更新 ${updatedCount} 本，跳过 ${skippedCount} 本`);
    } else {
      ElMessage.success(`一键分类完成，已更新 ${updatedCount} 本图书，跳过 ${skippedCount} 本`);
    }
  } catch (err: unknown) {
    if (isCancelError(err)) return;
    ElMessage.error(`一键分类失败：${getErrorMessage(err)}`);
  } finally {
    autoClassifying.value = false;
    stopAutoClassifyRequested.value = false;
  }
}

function stopAutoClassify() {
  stopAutoClassifyRequested.value = true;
  ElMessage.warning('已请求停止一键分类，当前这本处理结束后会停止');
}

async function fetchUncategorizedBooks(): Promise<BookListItem[]> {
  const result: BookListItem[] = [];
  let page = 1;
  while (true) {
    const data = await getBooks({ page, pageSize: 100 });
    result.push(...data.items.filter((book) => !book.category));
    if (page * data.pageSize >= data.total) break;
    page += 1;
  }
  return result;
}

async function confirmClassifyBook(
  book: BookListItem,
  result: ClassifyBookResponse,
  category: CategoryOption | null,
): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      [
        `图书：${book.title}`,
        `AI 推荐：${result.categoryCode} ${result.categoryName}`,
        `匹配分类：${category ? `${category.code} ${category.name}` : '未找到可写入的本地分类'}`,
        result.tags.length ? `推荐标签：${result.tags.join('、')}` : '推荐标签：无',
        result.reason ? `理由：${result.reason}` : '',
      ].filter(Boolean).join('\n'),
      '确认采用 AI 分类推荐',
      {
        type: category ? 'info' : 'warning',
        confirmButtonText: category ? '采用并更新' : '跳过',
        cancelButtonText: '跳过',
      },
    );
    return Boolean(category);
  } catch {
    return false;
  }
}

function resolveCategoryRecommendation(
  nodes: CategoryOption[],
  code: string,
  name: string,
): CategoryOption | null {
  const exactCodeMatch = findCategoryByCode(nodes, normalizeCategoryCode(code));
  if (exactCodeMatch) return exactCodeMatch;
  const nameMatch = findCategoryByName(nodes, name);
  if (nameMatch) return nameMatch;
  for (const fallbackCode of getCategoryFallbackCodes(code)) {
    const found = findCategoryByCode(nodes, fallbackCode);
    if (found) return found;
  }
  return null;
}

function findCategoryByCode(nodes: CategoryOption[], code: string): CategoryOption | null {
  for (const node of nodes) {
    if (node.code === code) return node;
    const found = node.children?.length ? findCategoryByCode(node.children, code) : null;
    if (found) return found;
  }
  return null;
}

function findCategoryByName(nodes: CategoryOption[], name: string): CategoryOption | null {
  const normalizedName = normalizeCategoryName(name);
  if (!normalizedName) return null;
  let looseMatch: CategoryOption | null = null;
  for (const node of nodes) {
    const nodeName = normalizeCategoryName(node.name);
    if (nodeName === normalizedName) return node;
    if (!looseMatch && (nodeName.includes(normalizedName) || normalizedName.includes(nodeName))) {
      looseMatch = node;
    }
    const found = node.children?.length ? findCategoryByName(node.children, name) : null;
    if (found) return found;
  }
  return looseMatch;
}

function normalizeCategoryCode(code: string): string {
  return code.trim().toUpperCase().replace(/\s+/g, '');
}

function normalizeCategoryName(name: string): string {
  return name.trim().replace(/[（）()《》\s]/g, '').replace(/类$/, '');
}

function getCategoryFallbackCodes(code: string): string[] {
  const normalized = normalizeCategoryCode(code);
  const fallbacks: string[] = [];
  const add = (candidate: string) => {
    if (candidate && candidate !== normalized && !fallbacks.includes(candidate)) fallbacks.push(candidate);
  };
  if (normalized.includes('.')) add(normalized.split('.')[0]);
  const letter = normalized.match(/^[A-Z]+/)?.[0] || '';
  const rest = normalized.slice(letter.length).replace(/[^0-9]/g, '');
  for (let len = rest.length - 1; letter && len >= 1; len--) add(`${letter}${rest.slice(0, len)}`);
  if (letter) add(letter);
  return fallbacks;
}

function isCancelError(err: unknown): boolean {
  return err === 'cancel' || err === 'close';
}

function getErrorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (err as { response?: { data?: { detail?: unknown; message?: string } } }).response?.data;
    if (data?.message) return data.message;
    if (typeof data?.detail === 'string') return data.detail;
  }
  if (err instanceof Error) return err.message;
  return '未知错误';
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
          <el-select
            v-model="aiSettings.defaultModel"
            allow-create
            clearable
            filterable
            placeholder="刷新后选择模型，或手动输入模型名"
            style="max-width: 360px"
            @change="setDefaultModel"
          >
            <el-option
              v-for="model in modelOptions"
              :key="model"
              :label="model"
              :value="model"
            />
          </el-select>
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
              共 {{ models.length }} 个可用模型，可在左侧下拉框中选择。
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
        type="info"
        :closable="false"
        show-icon
        title="支持导出或导入全部图书信息。Excel 模板可只填写书名，导入后再到藏书编辑中逐步补全。"
      />

      <el-form label-width="140px" style="margin-top: 16px">
        <el-form-item label="备份格式">
          <el-radio-group v-model="backupFormat">
            <el-radio-button value="xlsx">Excel</el-radio-button>
            <el-radio-button value="csv">CSV</el-radio-button>
            <el-radio-button value="json">JSON</el-radio-button>
          </el-radio-group>
          <div class="field-hint">Excel 适合日常编辑；CSV 便于批量整理；JSON 适合完整结构备份。</div>
        </el-form-item>
        <el-form-item label="模板与导出">
          <div class="backup-actions">
            <el-button :loading="downloadingTemplate" @click="handleDownloadTemplate">
              下载默认模板
            </el-button>
            <el-button type="primary" :loading="exporting" @click="handleExportBooks">
              导出全部图书
            </el-button>
          </div>
          <div class="field-hint">模板包含完整字段表头，也支持只填写 title / 书名后导入。</div>
        </el-form-item>
        <el-form-item label="导入图书">
          <input
            ref="fileInputRef"
            class="hidden-file-input"
            type="file"
            accept=".xlsx,.csv,.json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,application/json"
            @change="handleImportFileChange"
          />
          <div class="backup-import">
            <el-button :loading="importing" @click="openImportPicker">选择文件并预览</el-button>
            <el-button
              type="success"
              :disabled="!importPreview || importPreview.invalidRows > 0"
              :loading="importing"
              @click="handleConfirmImport"
            >
              确认导入
            </el-button>
          </div>
          <div v-if="backupFile" class="field-hint">已选择：{{ backupFile.name }}</div>
          <div v-if="importPreview" class="import-preview">
            <el-tag type="info">总行数 {{ importPreview.totalRows }}</el-tag>
            <el-tag type="success">可导入 {{ importPreview.validRows }}</el-tag>
            <el-tag :type="importPreview.invalidRows ? 'danger' : 'info'">错误 {{ importPreview.invalidRows }}</el-tag>
            <div v-if="importPreview.errors.length" class="import-errors">
              <div
                v-for="error in importPreview.errors.slice(0, 5)"
                :key="`${error.rowNumber}-${error.field}-${error.code}`"
              >
                第 {{ error.rowNumber }} 行：{{ error.message }}
              </div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="一键分类">
          <div class="backup-import">
            <el-button
              type="warning"
              :disabled="autoClassifying"
              :loading="autoClassifying && !stopAutoClassifyRequested"
              @click="handleAutoClassifyUncategorized"
            >
              AI 处理未分类图书
            </el-button>
            <el-button
              v-if="autoClassifying"
              type="danger"
              :disabled="stopAutoClassifyRequested"
              @click="stopAutoClassify"
            >
              关闭一键分类
            </el-button>
          </div>
          <div class="field-hint">
            自动查看藏书中所有未分类图书，逐本调用 AI 分类推荐；每本书都会弹出推荐分类和标签，确认后才写入。运行中可点击关闭一键分类停止后续处理。
          </div>
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

.backup-actions,
.backup-import,
.import-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.hidden-file-input {
  display: none;
}

.import-preview {
  width: 100%;
  margin-top: 8px;
}

.import-errors {
  width: 100%;
  color: var(--el-color-danger);
  font-size: 12px;
  line-height: 1.6;
}

.save-bar {
  padding: 8px 0;
}
</style>
