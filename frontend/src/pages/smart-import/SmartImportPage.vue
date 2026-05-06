<script setup lang="ts">
import { BrowserMultiFormatReader, type IScannerControls } from '@zxing/browser';
import { Back, Camera, Search } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { classifyBook, generateTags, getAIModels } from '@/api/ai';
import { getCategoryOptions, getLocationOptions } from '@/api/books';
import { createBook } from '@/api/books';
import { searchBooks, searchByISBN } from '@/api/search';
import AIRecommendationCard from '@/components/ai/AIRecommendationCard.vue';
import BookForm from '@/components/book/BookForm.vue';
import SearchResultCard from '@/components/search/SearchResultCard.vue';
import { createEmptyBookForm, type BookFormModel, type CategoryOption, type LocationOption } from '@/types/book';
import type { AIModel, AIStatus, ClassifyBookResponse, GenerateTagsResponse } from '@/types/ai';
import type { SearchResultItem } from '@/types/search';

type SearchType = 'isbn' | 'title' | 'title_publisher';
type PageStep = 'search' | 'draft';

const router = useRouter();

// ── Step control ────────────────────────────────────────────────────────────
const currentStep = ref<PageStep>('search');

// ── Search state ─────────────────────────────────────────────────────────────
const searchType = ref<SearchType>('title');
const searchQuery = ref('');
const searching = ref(false);
const searchError = ref('');
const searchResults = ref<SearchResultItem[]>([]);
const selectedResult = ref<SearchResultItem | null>(null);

// ── ISBN camera scanner ──────────────────────────────────────────────────────
const scannerDialogVisible = ref(false);
const scannerStarting = ref(false);
const scannerActive = ref(false);
const scannerError = ref('');
const scannerVideoRef = ref<HTMLVideoElement | null>(null);
let scannerControls: IScannerControls | null = null;

// ── Draft / form state ────────────────────────────────────────────────────────
const form = ref<BookFormModel>(createEmptyBookForm());
const categories = ref<CategoryOption[]>([]);
const locations = ref<LocationOption[]>([]);
const loadingOptions = ref(false);
const saving = ref(false);

// ── Douban enhance (ISBN→Douban secondary search) ─────────────────────────────
const doubanDialogVisible = ref(false);
const doubanSearching = ref(false);
const doubanResults = ref<SearchResultItem[]>([]);
const doubanError = ref('');

// ── AI state ─────────────────────────────────────────────────────────────────
const aiModels = ref<AIModel[]>([]);
const selectedModel = ref('');
const aiAvailable = ref(true);

const classifyStatus = ref<AIStatus>('idle');
const classifyResult = ref<ClassifyBookResponse | null>(null);
const classifyError = ref('');
const classifyDismissed = ref(false);

const tagsStatus = ref<AIStatus>('idle');
const tagsResult = ref<GenerateTagsResponse | null>(null);
const tagsError = ref('');
const tagsDismissed = ref(false);

// ── Init ─────────────────────────────────────────────────────────────────────
onMounted(() => {
  void loadFormOptions();
  void loadAIModels();
});

onBeforeUnmount(() => {
  stopBarcodeScanner();
});

async function loadFormOptions() {
  loadingOptions.value = true;
  try {
    const [catData, locData] = await Promise.all([getCategoryOptions(), getLocationOptions()]);
    categories.value = catData;
    locations.value = locData;
  } catch {
    ElMessage.error('分类或位置选项加载失败');
  } finally {
    loadingOptions.value = false;
  }
}

async function loadAIModels() {
  try {
    aiModels.value = await getAIModels();
    if (aiModels.value.length > 0) {
      selectedModel.value = aiModels.value[0].name;
    }
    aiAvailable.value = aiModels.value.length > 0;
  } catch {
    aiAvailable.value = false;
  }
}

// ── Search ────────────────────────────────────────────────────────────────────
async function handleSearch() {
  const query = searchQuery.value.trim();
  if (!query) {
    ElMessage.warning('请输入检索词');
    return;
  }

  searching.value = true;
  searchError.value = '';
  searchResults.value = [];

  try {
    if (searchType.value === 'isbn') {
      searchResults.value = await searchByISBN(query);
    } else if (searchType.value === 'title_publisher') {
      searchResults.value = await searchBooks(query, 30, { mode: 'title_publisher' });
    } else {
      searchResults.value = await searchBooks(query, 30);
    }

    if (searchResults.value.length === 0) {
      searchError.value = '未找到匹配结果，请尝试其他关键词';
    }
  } catch (err: unknown) {
    const message = getErrorMessage(err);
    searchError.value = `检索失败：${message}`;
  } finally {
    searching.value = false;
  }
}

async function openBarcodeScanner() {
  searchType.value = 'isbn';
  scannerDialogVisible.value = true;
  scannerError.value = '';
  await nextTick();
  await startBarcodeScanner();
}

async function startBarcodeScanner() {
  if (!scannerVideoRef.value || scannerActive.value || scannerStarting.value) return;

  scannerStarting.value = true;
  scannerError.value = '';

  try {
    const reader = new BrowserMultiFormatReader();
    scannerControls = await reader.decodeFromVideoDevice(
      undefined,
      scannerVideoRef.value,
      (result) => {
        const isbn = normalizeScannedIsbn(result?.getText());
        if (!isbn) return;

        searchQuery.value = isbn;
        ElMessage.success(`已识别 ISBN：${isbn}`);
        closeBarcodeScanner();
      },
    );
    scannerActive.value = true;
  } catch (err: unknown) {
    scannerError.value = getScannerErrorMessage(err);
    scannerActive.value = false;
  } finally {
    scannerStarting.value = false;
  }
}

function closeBarcodeScanner() {
  stopBarcodeScanner();
  scannerDialogVisible.value = false;
}

function stopBarcodeScanner() {
  scannerControls?.stop();
  scannerControls = null;
  scannerActive.value = false;
}

function handleSelectResult(result: SearchResultItem) {
  selectedResult.value = result;
  form.value = searchResultToForm(result);
  resetAIState();
  currentStep.value = 'draft';
}

function handleBackToSearch() {
  currentStep.value = 'search';
}

// ── AI Recommendations ────────────────────────────────────────────────────────
function resetAIState() {
  classifyStatus.value = aiAvailable.value ? 'idle' : 'unavailable';
  classifyResult.value = null;
  classifyError.value = '';
  classifyDismissed.value = false;
  tagsStatus.value = aiAvailable.value ? 'idle' : 'unavailable';
  tagsResult.value = null;
  tagsError.value = '';
  tagsDismissed.value = false;
}

async function handleClassify() {
  classifyStatus.value = 'loading';
  classifyError.value = '';
  try {
    classifyResult.value = await classifyBook({
      title: form.value.title,
      author: form.value.author,
      publisher: form.value.publisher,
      summary: form.value.summary,
      model: selectedModel.value || undefined,
    });
    classifyStatus.value = 'success';
  } catch (err: unknown) {
    classifyStatus.value = 'error';
    classifyError.value = getErrorMessage(err);
  }
}

function handleAcceptClassify() {
  if (!classifyResult.value) return;
  // Exact match first; fall back to progressively shorter prefix (e.g. "I247.5" → "I247" → "I")
  const code = classifyResult.value.categoryCode;
  let found = findCategoryByCode(categories.value, code);
  if (!found) {
    for (let len = code.length - 1; len >= 1 && !found; len--) {
      found = findCategoryByCode(categories.value, code.slice(0, len));
    }
  }
  if (found) {
    form.value.categoryId = found.id;
  } else {
    ElMessage.warning(`未找到匹配分类「${code}」，请在表单中手动选择`);
  }
  // Merge tags without duplicates
  const existing = new Set(form.value.tagNames);
  for (const tag of classifyResult.value.tags) {
    existing.add(tag);
  }
  form.value.tagNames = Array.from(existing);
  classifyDismissed.value = true;
  ElMessage.success('已采用 AI 分类推荐');
}

function handleDismissClassify() {
  classifyDismissed.value = true;
}

async function handleGenerateTags() {
  tagsStatus.value = 'loading';
  tagsError.value = '';
  try {
    tagsResult.value = await generateTags({
      title: form.value.title,
      author: form.value.author,
      publisher: form.value.publisher,
      summary: form.value.summary,
      model: selectedModel.value || undefined,
    });
    tagsStatus.value = 'success';
  } catch (err: unknown) {
    tagsStatus.value = 'error';
    tagsError.value = getErrorMessage(err);
  }
}

function handleAcceptTags() {
  if (!tagsResult.value) return;
  const existing = new Set(form.value.tagNames);
  for (const tag of tagsResult.value.tags) {
    existing.add(tag);
  }
  form.value.tagNames = Array.from(existing);
  tagsDismissed.value = true;
  ElMessage.success('已采用 AI 标签推荐');
}

function handleDismissTags() {
  tagsDismissed.value = true;
}

// ── Douban enhance ────────────────────────────────────────────────────────────
async function handleDoubanEnhance() {
  const title = form.value.title.trim();
  if (!title) {
    ElMessage.warning('书名为空，无法进行豆瓣补全');
    return;
  }
  doubanDialogVisible.value = true;
  doubanSearching.value = true;
  doubanError.value = '';
  doubanResults.value = [];
  try {
    doubanResults.value = await searchBooks(title, 10, { provider: 'douban' });
    if (doubanResults.value.length === 0) {
      doubanError.value = '豆瓣未找到相关书目，请尝试修改书名';
    }
  } catch (err: unknown) {
    doubanError.value = `豆瓣检索失败：${getErrorMessage(err)}`;
  } finally {
    doubanSearching.value = false;
  }
}

function handleApplyDoubanResult(result: SearchResultItem) {
  // Merge: only overwrite fields that are currently empty
  if (!form.value.author && result.author) form.value.author = result.author;
  if (!form.value.publisher && result.publisher) form.value.publisher = result.publisher;
  if (!form.value.publishYear && result.publishYear) form.value.publishYear = result.publishYear;
  if (!form.value.coverUrl && result.coverUrl) form.value.coverUrl = result.coverUrl;
  if (!form.value.summary && result.summary) form.value.summary = result.summary;
  if (!form.value.language && result.language) form.value.language = result.language;
  if (!form.value.pages && result.pages) form.value.pages = result.pages;
  // Always prefer Douban cover if available (better quality for Chinese books)
  if (result.coverUrl) form.value.coverUrl = result.coverUrl;
  doubanDialogVisible.value = false;
  ElMessage.success('已从豆瓣补全信息');
}

// ── Final Submit ──────────────────────────────────────────────────────────────
async function handleSubmit() {
  saving.value = true;
  try {
    const created = await createBook(form.value);
    ElMessage.success('图书已入库');
    await router.push({ name: 'book-detail', params: { id: created.id } });
  } catch (err: unknown) {
    ElMessage.error(`入库失败：${getErrorMessage(err)}`);
  } finally {
    saving.value = false;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function searchResultToForm(result: SearchResultItem): BookFormModel {
  const base = createEmptyBookForm();
  return {
    ...base,
    title: result.title,
    subtitle: result.subtitle,
    author: result.author,
    publisher: result.publisher,
    publishYear: result.publishYear,
    isbn: result.isbn,
    coverUrl: result.coverUrl,
    summary: result.summary,
    language: result.language || base.language,
    pages: result.pages,
  };
}

function findCategoryByCode(
  nodes: CategoryOption[],
  code: string,
): CategoryOption | null {
  for (const node of nodes) {
    if (node.code === code) return node;
    if (node.children?.length) {
      const found = findCategoryByCode(node.children, code);
      if (found) return found;
    }
  }
  return null;
}

function getErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return '未知错误';
}

function getScannerErrorMessage(err: unknown): string {
  if (err instanceof DOMException) {
    if (err.name === 'NotAllowedError') return '未获得摄像头权限，请允许浏览器访问摄像头后重试';
    if (err.name === 'NotFoundError') return '未检测到可用摄像头';
  }
  if (err instanceof Error) return err.message;
  return '摄像头启动失败，请检查浏览器权限或设备连接';
}

function normalizeScannedIsbn(value: string | undefined): string {
  const cleaned = (value || '').replace(/[^0-9Xx]/g, '').toUpperCase();
  if (cleaned.length === 13 && /^(978|979)\d{10}$/.test(cleaned)) return cleaned;
  if (cleaned.length === 10 && /^\d{9}[\dX]$/.test(cleaned)) return cleaned;
  return '';
}

function getAIButtonStatus(status: AIStatus): boolean {
  return status === 'loading';
}
</script>

<template>
  <section class="smart-import-page">
    <!-- Page header -->
    <div class="page-toolbar">
      <div>
        <h1>智能检索入库</h1>
        <p>通过 ISBN 或书名检索图书信息，支持 AI 分类与标签推荐</p>
      </div>
      <el-button :icon="Back" @click="router.push({ name: 'books' })">返回藏书</el-button>
    </div>

    <!-- Step indicators -->
    <el-steps :active="currentStep === 'search' ? 0 : 1" finish-status="success" simple>
      <el-step title="检索图书" />
      <el-step title="确认入库" />
    </el-steps>

    <!-- ── Step 1: Search ── -->
    <template v-if="currentStep === 'search'">
      <el-card class="search-card">
        <div class="search-controls">
          <el-radio-group v-model="searchType" class="search-type-group">
            <el-radio-button value="title">书名 / 书名+作者</el-radio-button>
            <el-radio-button value="title_publisher">书名+出版社</el-radio-button>
            <el-radio-button value="isbn">ISBN</el-radio-button>
          </el-radio-group>

          <div class="search-input-row">
            <el-input
              v-model="searchQuery"
              :placeholder="searchType === 'isbn' ? '输入 ISBN，如 9787108045269' : searchType === 'title_publisher' ? '输入「书名 出版社」，如「乡土中国 人民出版社」' : '输入书名，或「书名 作者」'"
              clearable
              size="large"
              @keyup.enter="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-button
              v-if="searchType === 'isbn'"
              :disabled="searching"
              :icon="Camera"
              size="large"
              @click="openBarcodeScanner"
            >
              扫码录入
            </el-button>
            <el-button
              :loading="searching"
              size="large"
              type="primary"
              @click="handleSearch"
            >
              检索
            </el-button>
          </div>

          <div class="search-hint">
            <span v-if="searchType === 'title'">
              支持单独书名（如「乡土中国」）或书名加作者（如「乡土中国 费孝通」），中文书名会自动扩展检索词并返回更多候选版本
            </span>
            <span v-else-if="searchType === 'title_publisher'">
              格式：「书名 出版社」，例如「围城 人民文学出版社」，适合同名书区分版本
            </span>
            <span v-else>
              支持 ISBN-10 或 ISBN-13，会自动标准化处理
            </span>
          </div>
        </div>
      </el-card>

      <el-dialog
        v-model="scannerDialogVisible"
        title="扫描 ISBN 条形码"
        width="560px"
        append-to-body
        @close="stopBarcodeScanner"
      >
        <div class="scanner-panel">
          <video
            ref="scannerVideoRef"
            class="scanner-video"
            muted
            playsinline
          />
          <div class="scanner-frame" aria-hidden="true" />
          <el-alert
            v-if="scannerError"
            :closable="false"
            :title="scannerError"
            show-icon
            type="error"
          />
          <p class="scanner-tip">
            将图书背面的 ISBN 条形码放入取景框。识别成功后会自动填入 ISBN 输入框。
          </p>
        </div>
        <template #footer>
          <el-button @click="closeBarcodeScanner">取消</el-button>
          <el-button
            :loading="scannerStarting"
            :disabled="scannerActive"
            type="primary"
            @click="startBarcodeScanner"
          >
            重新启动摄像头
          </el-button>
        </template>
      </el-dialog>

      <!-- Search results -->
      <div v-if="searching" class="results-area">
        <el-skeleton v-for="i in 3" :key="i" :rows="3" animated class="skeleton-card" />
      </div>

      <div v-else-if="searchError" class="results-area">
        <el-empty :description="searchError" :image-size="80">
          <el-button @click="searchError = ''">清除提示</el-button>
        </el-empty>
      </div>

      <div v-else-if="searchResults.length > 0" class="results-area">
        <div class="results-header">
          <span class="results-count">找到 {{ searchResults.length }} 条候选结果，点击「选择此版本」进入入库流程</span>
        </div>
        <div class="results-list">
          <SearchResultCard
            v-for="(result, index) in searchResults"
            :key="index"
            :result="result"
            :selected="selectedResult?.sourceId === result.sourceId"
            @select="handleSelectResult"
          />
        </div>
      </div>

      <div v-else class="results-area">
        <el-empty description="输入检索词后点击「检索」，系统将从联网数据源搜索图书信息" :image-size="80" />
      </div>
    </template>

    <!-- ── Step 2: Draft & Import ── -->
    <template v-else>
      <div class="draft-layout">
        <!-- Left: AI panel + selected book summary -->
        <aside class="draft-sidebar">
          <!-- Selected book summary -->
          <el-card v-if="selectedResult" class="selected-summary">
            <template #header>
              <div class="summary-header">
                <span>已选图书</span>
                <el-button link size="small" @click="handleBackToSearch">重新检索</el-button>
              </div>
            </template>
            <div class="summary-body">
              <el-image
                v-if="selectedResult.coverUrl"
                :src="selectedResult.coverUrl"
                class="summary-cover"
                fit="cover"
              />
              <div class="summary-info">
                <div class="summary-title">{{ selectedResult.title }}</div>
                <div v-if="selectedResult.author" class="summary-author">{{ selectedResult.author }}</div>
                <div v-if="selectedResult.isbn" class="summary-isbn">{{ selectedResult.isbn }}</div>
                <el-tag size="small" type="info">{{ selectedResult.source }}</el-tag>
              </div>
            </div>
            <div class="summary-footer">
              <el-button
                size="small"
                :loading="doubanSearching"
                @click="handleDoubanEnhance"
              >
                从豆瓣补全信息
              </el-button>
            </div>
          </el-card>

          <!-- Douban enhance dialog -->
          <el-dialog
            v-model="doubanDialogVisible"
            title="从豆瓣补全书目信息"
            width="560px"
            append-to-body
          >
            <div v-if="doubanSearching" class="douban-loading">
              <el-skeleton v-for="i in 3" :key="i" :rows="2" animated />
            </div>
            <div v-else-if="doubanError" class="douban-error">
              <el-alert :title="doubanError" :closable="false" type="warning" show-icon />
            </div>
            <div v-else class="douban-results">
              <p class="douban-hint">选择最匹配的版本，封面、作者、年份等字段将补充到当前表单中</p>
              <div class="results-list">
                <SearchResultCard
                  v-for="(result, index) in doubanResults"
                  :key="index"
                  :result="result"
                  @select="handleApplyDoubanResult"
                />
              </div>
            </div>
            <template #footer>
              <el-button @click="doubanDialogVisible = false">取消</el-button>
            </template>
          </el-dialog>

          <!-- AI model selector -->
          <el-card v-if="aiAvailable && aiModels.length > 0" class="ai-model-card">
            <template #header>AI 设置</template>
            <el-select v-model="selectedModel" placeholder="选择模型" size="small" style="width: 100%">
              <el-option
                v-for="model in aiModels"
                :key="model.name"
                :label="model.name"
                :value="model.name"
              />
            </el-select>
          </el-card>

          <!-- Classification recommendation -->
          <AIRecommendationCard
            title="AI 分类推荐"
            :status="!aiAvailable ? 'unavailable' : (classifyDismissed ? 'idle' : classifyStatus)"
            :error-message="classifyError"
            @accept="handleAcceptClassify"
            @dismiss="handleDismissClassify"
            @retry="handleClassify"
          >
            <template #idle>
              <div v-if="!classifyDismissed" class="ai-idle-content">
                <p>点击下方按钮，让 AI 推荐图书分类</p>
                <el-button
                  :disabled="!aiAvailable"
                  :loading="getAIButtonStatus(classifyStatus)"
                  size="small"
                  type="primary"
                  @click="handleClassify"
                >
                  获取分类推荐
                </el-button>
              </div>
              <div v-else class="ai-done-content">
                <el-text type="success" size="small">已处理分类推荐</el-text>
              </div>
            </template>

            <div v-if="classifyResult" class="classify-result">
              <div class="result-row">
                <span class="result-label">分类</span>
                <el-tag>{{ classifyResult.categoryCode }} {{ classifyResult.categoryName }}</el-tag>
              </div>
              <div class="result-row">
                <span class="result-label">置信度</span>
                <el-progress
                  :percentage="Math.round(classifyResult.confidence * 100)"
                  :stroke-width="8"
                  style="width: 120px"
                />
              </div>
              <div v-if="classifyResult.tags.length" class="result-row result-tags">
                <span class="result-label">推荐标签</span>
                <div class="tags-list">
                  <el-tag
                    v-for="tag in classifyResult.tags"
                    :key="tag"
                    size="small"
                    type="success"
                  >
                    {{ tag }}
                  </el-tag>
                </div>
              </div>
              <div v-if="classifyResult.reason" class="result-reason">
                {{ classifyResult.reason }}
              </div>
            </div>
          </AIRecommendationCard>

          <!-- Tags recommendation -->
          <AIRecommendationCard
            title="AI 标签推荐"
            :status="!aiAvailable ? 'unavailable' : (tagsDismissed ? 'idle' : tagsStatus)"
            :error-message="tagsError"
            @accept="handleAcceptTags"
            @dismiss="handleDismissTags"
            @retry="handleGenerateTags"
          >
            <template #idle>
              <div v-if="!tagsDismissed" class="ai-idle-content">
                <p>点击下方按钮，让 AI 生成标签</p>
                <el-button
                  :disabled="!aiAvailable"
                  :loading="getAIButtonStatus(tagsStatus)"
                  size="small"
                  type="primary"
                  @click="handleGenerateTags"
                >
                  生成标签推荐
                </el-button>
              </div>
              <div v-else class="ai-done-content">
                <el-text type="success" size="small">已处理标签推荐</el-text>
              </div>
            </template>

            <div v-if="tagsResult" class="tags-result">
              <div class="tags-list">
                <el-tag
                  v-for="tag in tagsResult.tags"
                  :key="tag"
                  size="small"
                  type="success"
                >
                  {{ tag }}
                </el-tag>
              </div>
            </div>
          </AIRecommendationCard>

          <el-alert
            v-if="!aiAvailable"
            :closable="false"
            description="Ollama 服务当前不可用，AI 推荐功能已禁用。您仍可手动填写分类和标签后完成入库。"
            show-icon
            title="AI 服务不可用"
            type="warning"
          />
        </aside>

        <!-- Right: Book form -->
        <div class="draft-form">
          <el-card>
            <template #header>
              <div class="form-header">
                <span>确认图书信息</span>
                <span class="form-hint">请核对信息，可直接修改后入库</span>
              </div>
            </template>

            <BookForm
              v-model="form"
              v-loading="loadingOptions"
              :categories="categories"
              :loading="saving"
              :locations="locations"
              @cancel="handleBackToSearch"
              @submit="handleSubmit"
            />
          </el-card>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.smart-import-page {
  display: grid;
  gap: 16px;
}

.page-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-toolbar h1 {
  margin: 0;
  font-size: 24px;
}

.page-toolbar p {
  margin: 6px 0 0;
  color: var(--app-muted, var(--el-text-color-secondary));
}

/* Search card */
.search-card :deep(.el-card__body) {
  padding: 20px;
}

.search-controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.search-input-row {
  display: flex;
  gap: 10px;
}

.search-hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.scanner-panel {
  position: relative;
  display: grid;
  gap: 12px;
}

.scanner-video {
  width: 100%;
  aspect-ratio: 4 / 3;
  background: #111827;
  border-radius: 8px;
  object-fit: cover;
}

.scanner-frame {
  position: absolute;
  top: 18%;
  left: 12%;
  right: 12%;
  height: 36%;
  border: 2px solid var(--el-color-primary);
  border-radius: 8px;
  box-shadow: 0 0 0 999px rgb(0 0 0 / 18%);
  pointer-events: none;
}

.scanner-tip {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

/* Results */
.results-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 120px;
}

.results-header {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.results-list {
  display: grid;
  gap: 12px;
}

.skeleton-card {
  padding: 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
}

/* Draft layout */
.draft-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  align-items: start;
}

@media (max-width: 960px) {
  .draft-layout {
    grid-template-columns: 1fr;
  }
}

.draft-sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: sticky;
  top: 16px;
}

/* Selected summary */
.summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.summary-body {
  display: flex;
  gap: 10px;
}

.summary-cover {
  width: 56px;
  height: 76px;
  border-radius: 4px;
  flex-shrink: 0;
  object-fit: cover;
}

.summary-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.summary-title {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-author,
.summary-isbn {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.summary-footer {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
  display: flex;
  justify-content: flex-end;
}

.douban-loading {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.douban-hint {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.douban-results {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.douban-error {
  padding: 8px 0;
}

/* AI results */
.classify-result,
.tags-result {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.result-tags {
  align-items: flex-start;
}

.result-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  min-width: 48px;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.result-reason {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  padding: 6px 8px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}

.ai-idle-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ai-idle-content p {
  margin: 0;
  font-size: 13px;
}

.ai-done-content {
  font-size: 13px;
}

/* Form header */
.form-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.form-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: 400;
}

.draft-form :deep(.book-form .form-actions) {
  background: var(--el-bg-color);
}
</style>
