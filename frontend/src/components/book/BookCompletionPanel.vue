<script setup lang="ts">
import type { AxiosError } from 'axios';
import { ElMessage } from 'element-plus';
import { computed, onMounted, ref } from 'vue';

import { classifyBook, getAIModels, recommendBookContent } from '@/api/ai';
import {
  fetchSearchTask,
  searchBooks,
  searchBooksProgressive,
  searchByISBN,
  searchByISBNProgressive,
  type ProgressiveSearchResponse,
} from '@/api/search';
import { fetchAIModelSettings } from '@/api/settings';
import AIRecommendationCard from '@/components/ai/AIRecommendationCard.vue';
import SearchResultCard from '@/components/search/SearchResultCard.vue';
import type {
  AIModel,
  AIStatus,
  BookContentCandidate,
  BookContentFields,
  ClassifyBookResponse,
  RecommendBookContentResponse,
} from '@/types/ai';
import type { BookFormModel, CategoryOption } from '@/types/book';
import type { SearchResultItem } from '@/types/search';

const form = defineModel<BookFormModel>({ required: true });

const props = defineProps<{
  categories: CategoryOption[];
}>();

const enhanceDialogVisible = ref(false);
const enhanceSearching = ref(false);
const enhanceResults = ref<SearchResultItem[]>([]);
const enhanceError = ref('');
const activeEnhanceSource = ref('all');
const SOURCE_LABELS: Record<string, string> = {
  all: '全部',
  nlc: 'NLC（国家图书馆）',
  open_library: 'Open Library',
  google_books: 'Google Books',
  isbn_work: 'ISBN Work',
  douban: '豆瓣读书',
};
const enhanceSourceTabs = computed(() => {
  const counts = new Map<string, number>();
  enhanceResults.value.forEach((item) => counts.set(item.source, (counts.get(item.source) || 0) + 1));
  return [
    { source: 'all', label: '全部', count: enhanceResults.value.length },
    ...Array.from(counts.entries()).map(([source, count]) => ({
      source,
      label: SOURCE_LABELS[source] || source,
      count,
    })),
  ];
});
const displayedEnhanceResults = computed(() =>
  activeEnhanceSource.value === 'all'
    ? enhanceResults.value
    : enhanceResults.value.filter((item) => item.source === activeEnhanceSource.value),
);

const aiModels = ref<AIModel[]>([]);
const selectedModel = ref('');
const aiAvailable = ref(true);
const aiModelOptions = computed(() => {
  const names = aiModels.value.map((model) => model.name);
  if (selectedModel.value && !names.includes(selectedModel.value)) {
    return [{ name: selectedModel.value }, ...aiModels.value];
  }
  return aiModels.value;
});

const classifyStatus = ref<AIStatus>('idle');
const classifyResult = ref<ClassifyBookResponse | null>(null);
const classifyError = ref('');
const classifyDismissed = ref(false);

const contentStatus = ref<AIStatus>('idle');
const contentResult = ref<RecommendBookContentResponse | null>(null);
const contentError = ref('');
const contentDismissed = ref(false);

onMounted(() => {
  void loadAIModels();
});

async function loadAIModels() {
  try {
    const [models, settings] = await Promise.all([getAIModels(), fetchAIModelSettings()]);
    aiModels.value = models;
    selectedModel.value = settings.defaultModel || models[0]?.name || '';
    aiAvailable.value = aiModels.value.length > 0;
  } catch {
    aiAvailable.value = false;
    classifyStatus.value = 'unavailable';
    contentStatus.value = 'unavailable';
  }
}

async function handleExternalEnhance() {
  if (!form.value.title.trim() && !form.value.isbn.trim()) {
    ElMessage.warning('书名和 ISBN 为空，无法进行其他数据源补全');
    return;
  }
  enhanceDialogVisible.value = true;
  enhanceSearching.value = true;
  enhanceError.value = '';
  enhanceResults.value = [];
  activeEnhanceSource.value = 'all';
  try {
    enhanceResults.value = await fetchEnhanceCandidatesProgressively(20, (items, isComplete) => {
      enhanceResults.value = items;
      if (items.length > 0 || isComplete) {
        enhanceSearching.value = false;
      }
    });
    if (enhanceResults.value.length === 0) {
      enhanceError.value = '其他数据源未找到可补全的书目，请尝试补充书名、作者、出版社或 ISBN';
    }
  } catch (err: unknown) {
    enhanceError.value = `其他数据源补全检索失败：${getErrorMessage(err)}`;
  } finally {
    enhanceSearching.value = false;
  }
}

function handleApplyEnhanceResult(result: SearchResultItem) {
  const changed = applyContentFieldsToEmptyForm(searchResultToContentCandidate(result));
  enhanceDialogVisible.value = false;
  ElMessage.success(changed > 0 ? `已从 ${result.source} 补全 ${changed} 项信息` : '当前空字段未在该数据源中找到可补全内容');
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
  const code = normalizeCategoryCode(classifyResult.value.categoryCode);
  const found = resolveCategoryRecommendation(props.categories, code, classifyResult.value.categoryName);
  if (found) {
    form.value.categoryId = found.id;
  } else {
    ElMessage.warning(`未找到匹配分类「${code}」，请在表单中手动选择`);
  }
  const tags = new Set(form.value.tagNames);
  for (const tag of classifyResult.value.tags) {
    tags.add(tag);
  }
  form.value.tagNames = Array.from(tags);
  classifyDismissed.value = true;
  ElMessage.success('已采用 AI 分类和标签推荐');
}

async function handleGenerateContentRecommendation() {
  const missingFields = getMissingContentFields();
  if (missingFields.length === 0) {
    ElMessage.info('当前图书信息已较完整，暂无需要 AI 补全的空字段');
    return;
  }
  contentStatus.value = 'loading';
  contentError.value = '';
  try {
    const candidates = await fetchEnhanceCandidates(12);
    contentResult.value = await recommendBookContent({
      current: bookFormToContentFields(),
      candidates: candidates.map(searchResultToContentCandidate),
      missingFields,
      model: selectedModel.value || undefined,
    });
    contentStatus.value = 'success';
  } catch (err: unknown) {
    contentStatus.value = 'error';
    contentError.value = getErrorMessage(err);
  }
}

function handleAcceptContentRecommendation() {
  if (!contentResult.value) return;
  const changed = applyContentFieldsToEmptyForm(contentResult.value.recommended);
  contentDismissed.value = true;
  ElMessage.success(changed > 0 ? `已采用 ${changed} 项 AI 检索内容推荐` : '暂无可填充的空字段');
}

async function fetchEnhanceCandidatesProgressively(
  limit = 20,
  onUpdate?: (items: SearchResultItem[], isComplete: boolean) => void,
): Promise<SearchResultItem[]> {
  const requests: Array<Promise<ProgressiveSearchResponse>> = [];
  const title = form.value.title.trim();
  const author = form.value.author.trim();
  const publisher = form.value.publisher.trim();
  const isbn = form.value.isbn.trim();

  if (isbn) requests.push(searchByISBNProgressive(isbn));
  if (title && author) requests.push(searchBooksProgressive(`${title} ${author}`, limit));
  if (title && publisher) requests.push(searchBooksProgressive(`${title} ${publisher}`, limit, { mode: 'title_publisher' }));
  if (title) requests.push(searchBooksProgressive(title, limit));

  const initial = await Promise.allSettled(requests);
  let collected = initial
    .filter((item): item is PromiseFulfilledResult<ProgressiveSearchResponse> => item.status === 'fulfilled')
    .flatMap((item) => item.value.items);
  let results = dedupeSearchResults(collected).slice(0, limit);
  let pendingTaskIds = initial
    .filter((item): item is PromiseFulfilledResult<ProgressiveSearchResponse> => item.status === 'fulfilled')
    .map((item) => item.value.taskId)
    .filter((taskId): taskId is string => Boolean(taskId));
  onUpdate?.(results, pendingTaskIds.length === 0);

  while (pendingTaskIds.length > 0) {
    await delay(1000);
    const polled = await Promise.allSettled(pendingTaskIds.map(fetchSearchTask));
    pendingTaskIds = [];
    for (const item of polled) {
      if (item.status !== 'fulfilled') continue;
      collected = [...collected, ...item.value.items];
      if (item.value.taskId) {
        pendingTaskIds.push(item.value.taskId);
      }
    }
    results = dedupeSearchResults(collected).slice(0, limit);
    onUpdate?.(results, pendingTaskIds.length === 0);
  }

  return results;
}

async function fetchEnhanceCandidates(limit = 20): Promise<SearchResultItem[]> {
  const tasks: Array<Promise<SearchResultItem[]>> = [];
  const title = form.value.title.trim();
  const author = form.value.author.trim();
  const publisher = form.value.publisher.trim();
  const isbn = form.value.isbn.trim();

  if (isbn) tasks.push(searchByISBN(isbn));
  if (title && author) tasks.push(searchBooks(`${title} ${author}`, limit));
  if (title && publisher) tasks.push(searchBooks(`${title} ${publisher}`, limit, { mode: 'title_publisher' }));
  if (title) tasks.push(searchBooks(title, limit));

  const settled = await Promise.allSettled(tasks);
  const fulfilled = settled
    .filter((item): item is PromiseFulfilledResult<SearchResultItem[]> => item.status === 'fulfilled')
    .flatMap((item) => item.value);
  return dedupeSearchResults(fulfilled).slice(0, limit);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function dedupeSearchResults(items: SearchResultItem[]): SearchResultItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.source}:${item.sourceId || item.isbn || item.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function searchResultToContentCandidate(result: SearchResultItem): BookContentCandidate {
  return {
    source: result.source,
    sourceId: result.sourceId,
    title: result.title,
    subtitle: result.subtitle,
    author: result.author,
    publisher: result.publisher,
    publishYear: result.publishYear,
    isbn: result.isbn,
    language: result.language,
    pages: result.pages,
    coverUrl: result.coverUrl,
    summary: result.summary,
    raw: result.raw,
  };
}

function applyContentFieldsToEmptyForm(fields: BookContentFields): number {
  let changed = 0;
  const fillText = (key: keyof BookFormModel, value: string | undefined | null) => {
    const current = form.value[key];
    if (typeof current === 'string' && !current.trim() && value?.trim()) {
      (form.value[key] as string) = value.trim();
      changed += 1;
    }
  };
  const fillNumber = (key: keyof BookFormModel, value: number | undefined | null) => {
    if ((form.value[key] === null || form.value[key] === undefined) && value !== null && value !== undefined) {
      (form.value[key] as number | null) = value;
      changed += 1;
    }
  };

  fillText('title', fields.title);
  fillText('subtitle', fields.subtitle);
  fillText('author', fields.author);
  fillText('translator', fields.translator);
  fillText('publisher', fields.publisher);
  fillNumber('publishYear', fields.publishYear);
  fillText('isbn', fields.isbn);
  fillText('language', fields.language);
  fillNumber('pages', fields.pages);
  fillText('coverUrl', fields.coverUrl);
  fillText('summary', fields.summary);
  fillText('authorIntro', fields.authorIntro);
  fillText('binding', fields.binding);
  fillText('series', fields.series);
  fillText('note', fields.note);
  return changed;
}

function bookFormToContentFields(): BookContentFields {
  return {
    title: form.value.title,
    subtitle: form.value.subtitle,
    author: form.value.author,
    translator: form.value.translator,
    publisher: form.value.publisher,
    publishYear: form.value.publishYear,
    isbn: form.value.isbn,
    language: form.value.language,
    pages: form.value.pages,
    coverUrl: form.value.coverUrl,
    summary: form.value.summary,
    authorIntro: form.value.authorIntro,
    binding: form.value.binding,
    series: form.value.series,
    note: form.value.note,
  };
}

function getMissingContentFields(): string[] {
  const checks: Array<[keyof BookFormModel, string]> = [
    ['subtitle', 'subtitle'],
    ['author', 'author'],
    ['translator', 'translator'],
    ['publisher', 'publisher'],
    ['publishYear', 'publish_year'],
    ['isbn', 'isbn'],
    ['language', 'language'],
    ['pages', 'pages'],
    ['coverUrl', 'cover_url'],
    ['summary', 'summary'],
    ['authorIntro', 'author_intro'],
    ['binding', 'binding'],
    ['series', 'series'],
    ['note', 'note'],
  ];
  return checks.filter(([key]) => isFormFieldEmpty(key)).map(([, apiName]) => apiName);
}

function isFormFieldEmpty(key: keyof BookFormModel): boolean {
  const value = form.value[key];
  if (typeof value === 'string') return !value.trim();
  return value === null || value === undefined;
}

function getRecommendedContentEntries() {
  if (!contentResult.value) return [];
  const labels: Array<[keyof BookContentFields, string]> = [
    ['subtitle', '副标题'],
    ['author', '作者'],
    ['translator', '译者'],
    ['publisher', '出版社'],
    ['publishYear', '出版年份'],
    ['isbn', 'ISBN'],
    ['language', '语言'],
    ['pages', '页数'],
    ['coverUrl', '封面 URL'],
    ['summary', '内容简介'],
    ['authorIntro', '作者简介'],
    ['binding', '装帧'],
    ['series', '丛书'],
    ['note', '备注'],
  ];
  return labels
    .map(([key, label]) => ({ label, value: contentResult.value?.recommended[key] }))
    .filter((item) => item.value !== null && item.value !== undefined && String(item.value).trim());
}

function resolveCategoryRecommendation(nodes: CategoryOption[], code: string, name: string): CategoryOption | null {
  const exactCodeMatch = findCategoryByCode(nodes, code);
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
    if (!looseMatch && (nodeName.includes(normalizedName) || normalizedName.includes(nodeName))) looseMatch = node;
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

function getErrorMessage(err: unknown): string {
  const axiosError = err as AxiosError<{ detail?: unknown; message?: string }>;
  if (axiosError.response?.data) {
    const { detail, message } = axiosError.response.data;
    if (typeof message === 'string' && message) return message;
    if (typeof detail === 'string' && detail) return detail;
  }
  if (err instanceof Error) return err.message;
  return '未知错误';
}
</script>

<template>
  <div class="completion-panel">
    <el-card>
      <template #header>信息补全</template>
      <div class="panel-actions">
        <el-button type="primary" :loading="enhanceSearching" @click="handleExternalEnhance">
          从其他补全信息
        </el-button>
        <p>按 ISBN、书名+作者、书名+出版社和书名检索外部书源，只填充当前为空的字段，可重复补全。</p>
      </div>
    </el-card>

    <el-card v-if="aiAvailable && aiModels.length > 0">
      <template #header>AI 设置</template>
      <el-select v-model="selectedModel" placeholder="选择模型" size="small" style="width: 100%">
        <el-option v-for="model in aiModelOptions" :key="model.name" :label="model.name" :value="model.name" />
      </el-select>
    </el-card>

    <AIRecommendationCard
      title="AI 分类推荐"
      :status="!aiAvailable ? 'unavailable' : (classifyDismissed ? 'idle' : classifyStatus)"
      :error-message="classifyError"
      @accept="handleAcceptClassify"
      @dismiss="classifyDismissed = true"
      @retry="handleClassify"
    >
      <template #idle>
        <div v-if="!classifyDismissed" class="ai-idle-content">
          <p>根据当前书目信息推荐分类和标签</p>
          <el-button :disabled="!aiAvailable" :loading="classifyStatus === 'loading'" size="small" type="primary" @click="handleClassify">
            获取分类推荐
          </el-button>
        </div>
        <el-text v-else type="success" size="small">已处理分类推荐</el-text>
      </template>

      <div v-if="classifyResult" class="result-list">
        <div><span>分类</span><el-tag>{{ classifyResult.categoryCode }} {{ classifyResult.categoryName }}</el-tag></div>
        <div v-if="classifyResult.tags.length"><span>标签</span><el-tag v-for="tag in classifyResult.tags" :key="tag" size="small" type="success">{{ tag }}</el-tag></div>
        <p v-if="classifyResult.reason">{{ classifyResult.reason }}</p>
      </div>
    </AIRecommendationCard>

    <AIRecommendationCard
      title="AI 检索内容推荐"
      :status="!aiAvailable ? 'unavailable' : (contentDismissed ? 'idle' : contentStatus)"
      :error-message="contentError"
      @accept="handleAcceptContentRecommendation"
      @dismiss="contentDismissed = true"
      @retry="handleGenerateContentRecommendation"
    >
      <template #idle>
        <div v-if="!contentDismissed" class="ai-idle-content">
          <p>先检索外部数据源，再由 AI 整理当前空字段</p>
          <el-button :disabled="!aiAvailable" :loading="contentStatus === 'loading'" size="small" type="primary" @click="handleGenerateContentRecommendation">
            生成内容推荐
          </el-button>
        </div>
        <el-text v-else type="success" size="small">已处理内容推荐</el-text>
      </template>

      <div v-if="contentResult" class="result-list">
        <div v-for="item in getRecommendedContentEntries()" :key="item.label">
          <span>{{ item.label }}</span>
          <em>{{ item.value }}</em>
        </div>
        <p v-if="contentResult.sourceSummary">{{ contentResult.sourceSummary }}</p>
        <p v-if="contentResult.reason">{{ contentResult.reason }}</p>
      </div>
    </AIRecommendationCard>

    <el-alert
      v-if="!aiAvailable"
      :closable="false"
      description="Ollama 服务当前不可用，AI 推荐功能已禁用。"
      show-icon
      title="AI 服务不可用"
      type="warning"
    />

    <el-dialog v-model="enhanceDialogVisible" title="从其他数据源补全书目信息" width="620px" append-to-body>
      <div v-if="enhanceSearching" class="enhance-loading">
        <el-skeleton v-for="i in 3" :key="i" :rows="2" animated />
      </div>
      <el-alert v-else-if="enhanceError" :title="enhanceError" :closable="false" type="warning" show-icon />
      <div v-else class="enhance-results">
        <p>选择一个数据源版本，仅补充当前为空的字段。可重复打开并选择其他数据源累计补全。</p>
        <el-radio-group v-model="activeEnhanceSource" class="source-filter">
          <el-radio-button
            v-for="tab in enhanceSourceTabs"
            :key="tab.source"
            :value="tab.source"
          >
            {{ tab.label }}（{{ tab.count }}）
          </el-radio-button>
        </el-radio-group>
        <SearchResultCard
          v-for="(result, index) in displayedEnhanceResults"
          :key="index"
          :result="result"
          @select="handleApplyEnhanceResult"
        />
      </div>
      <template #footer>
        <el-button @click="enhanceDialogVisible = false">取消</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.completion-panel {
  display: grid;
  gap: 12px;
}

.panel-actions {
  display: grid;
  gap: 8px;
}

.panel-actions p,
.ai-idle-content p,
.enhance-results p,
.result-list p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.ai-idle-content {
  display: grid;
  gap: 8px;
}

.result-list {
  display: grid;
  gap: 8px;
}

.result-list > div {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.result-list span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.result-list em {
  font-style: normal;
  line-height: 1.5;
}

.enhance-loading,
.enhance-results {
  display: grid;
  gap: 12px;
}

.source-filter {
  justify-self: start;
}
</style>
