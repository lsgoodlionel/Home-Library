<script setup lang="ts">
import { BrowserMultiFormatReader, type IScannerControls } from '@zxing/browser';
import { Back, Camera, Search } from '@element-plus/icons-vue';
import type { AxiosError } from 'axios';
import { ElMessage } from 'element-plus';
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { classifyBook, getAIModels, recommendBookContent } from '@/api/ai';
import { getCategoryOptions, getLocationOptions } from '@/api/books';
import { createBook } from '@/api/books';
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
import BookForm from '@/components/book/BookForm.vue';
import SearchResultCard from '@/components/search/SearchResultCard.vue';
import { createEmptyBookForm, type BookFormModel, type CategoryOption, type LocationOption } from '@/types/book';
import type {
  AIModel,
  AIStatus,
  BookContentCandidate,
  BookContentFields,
  ClassifyBookResponse,
  RecommendBookContentResponse,
} from '@/types/ai';
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
const activeSearchSource = ref('all');
const SOURCE_LABELS: Record<string, string> = {
  all: '全部',
  nlc: 'NLC（国家图书馆）',
  open_library: 'Open Library',
  google_books: 'Google Books',
  isbn_work: 'ISBN Work',
  douban: '豆瓣读书',
};
const sourceTabs = computed(() => {
  const counts = new Map<string, number>();
  searchResults.value.forEach((item) => counts.set(item.source, (counts.get(item.source) || 0) + 1));
  return [
    { source: 'all', label: '全部', count: searchResults.value.length },
    ...Array.from(counts.entries()).map(([source, count]) => ({
      source,
      label: SOURCE_LABELS[source] || source,
      count,
    })),
  ];
});
const displayedSearchResults = computed(() =>
  activeSearchSource.value === 'all'
    ? searchResults.value
    : searchResults.value.filter((item) => item.source === activeSearchSource.value),
);

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

// ── External source enhancement ──────────────────────────────────────────────
const enhanceDialogVisible = ref(false);
const enhanceSearching = ref(false);
const enhanceResults = ref<SearchResultItem[]>([]);
const enhanceError = ref('');

// ── AI state ─────────────────────────────────────────────────────────────────
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
    const [models, settings] = await Promise.all([getAIModels(), fetchAIModelSettings()]);
    aiModels.value = models;
    selectedModel.value = settings.defaultModel || models[0]?.name || '';
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
  activeSearchSource.value = 'all';

  try {
    searchResults.value = await searchCandidatesProgressively(query, 30, (items, isComplete) => {
      searchResults.value = items;
      if (items.length > 0 || isComplete) {
        searching.value = false;
      }
    });

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

async function searchCandidatesProgressively(
  query: string,
  limit = 30,
  onUpdate?: (items: SearchResultItem[], isComplete: boolean) => void,
): Promise<SearchResultItem[]> {
  const response = searchType.value === 'isbn'
    ? await searchByISBNProgressive(query)
    : await searchBooksProgressive(query, limit, searchType.value === 'title_publisher' ? { mode: 'title_publisher' } : undefined);
  let results = dedupeSearchResults(response.items).slice(0, limit);
  let taskId = response.taskId;
  onUpdate?.(results, !taskId);

  while (taskId) {
    await delay(1000);
    const next = await fetchSearchTask(taskId);
    results = dedupeSearchResults([...results, ...next.items]).slice(0, limit);
    taskId = next.taskId;
    onUpdate?.(results, !taskId);
  }

  return results;
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
  contentStatus.value = aiAvailable.value ? 'idle' : 'unavailable';
  contentResult.value = null;
  contentError.value = '';
  contentDismissed.value = false;
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
  const aiCode = normalizeCategoryCode(classifyResult.value.categoryCode);
  const aiName = classifyResult.value.categoryName;
  const found = resolveCategoryRecommendation(categories.value, aiCode, aiName);
  if (found) {
    form.value.categoryId = found.id;
    const actualLabel = `${found.code} ${found.name}`;
    if (found.code.toUpperCase() === aiCode) {
      ElMessage.success(`已采用分类「${actualLabel}」和标签推荐`);
    } else {
      ElMessage.success(`已采用分类「${actualLabel}」和标签推荐（AI推荐「${aiCode} ${aiName}」，已自动匹配至最近分类）`);
    }
  } else {
    ElMessage.warning(`未找到匹配分类「${aiCode}」，请在表单中手动选择`);
  }
  // Merge tags without duplicates
  const existing = new Set(form.value.tagNames);
  for (const tag of classifyResult.value.tags) {
    existing.add(tag);
  }
  form.value.tagNames = Array.from(existing);
  classifyDismissed.value = true;
}

function handleDismissClassify() {
  classifyDismissed.value = true;
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

function handleDismissContentRecommendation() {
  contentDismissed.value = true;
}

// ── External source enhancement ──────────────────────────────────────────────
async function handleExternalEnhance() {
  if (!form.value.title.trim() && !form.value.isbn.trim()) {
    ElMessage.warning('书名和 ISBN 为空，无法进行其他数据源补全');
    return;
  }
  enhanceDialogVisible.value = true;
  enhanceSearching.value = true;
  enhanceError.value = '';
  enhanceResults.value = [];
  try {
    enhanceResults.value = await fetchEnhanceCandidatesProgressively(20, (items, isComplete) => {
      enhanceResults.value = items;
      if (items.length > 0 || isComplete) {
        enhanceSearching.value = false;
      }
    });
    if (enhanceResults.value.length === 0) {
      enhanceError.value = '其他数据源未找到可补全的书目，请尝试修改书名、作者、出版社或 ISBN';
    }
  } catch (err: unknown) {
    enhanceError.value = `其他数据源补全检索失败：${getErrorMessage(err)}`;
  } finally {
    enhanceSearching.value = false;
  }
}

function handleApplyEnhanceResult(result: SearchResultItem) {
  const changed = applySearchResultToEmptyForm(result);
  enhanceDialogVisible.value = false;
  ElMessage.success(changed > 0 ? `已从 ${result.source} 补全 ${changed} 项信息` : '当前空字段未在该数据源中找到可补全内容');
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
  const selectedKey = selectedResult.value ? searchResultKey(selectedResult.value) : '';
  return items.filter((item) => {
    const key = searchResultKey(item);
    if (key === selectedKey || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function searchResultKey(item: SearchResultItem): string {
  return `${item.source}:${item.sourceId || item.isbn || item.title}`;
}

function applySearchResultToEmptyForm(result: SearchResultItem): number {
  return applyContentFieldsToEmptyForm(searchResultToContentCandidate(result));
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
  return checks
    .filter(([key]) => isFormFieldEmpty(key))
    .map(([, apiName]) => apiName);
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

function findCategoryByName(
  nodes: CategoryOption[],
  name: string,
): CategoryOption | null {
  const normalizedName = normalizeCategoryName(name);
  if (!normalizedName) return null;

  let looseMatch: CategoryOption | null = null;
  for (const node of nodes) {
    const nodeName = normalizeCategoryName(node.name);
    if (nodeName === normalizedName) return node;
    if (!looseMatch && (nodeName.includes(normalizedName) || normalizedName.includes(nodeName))) {
      looseMatch = node;
    }
    if (node.children?.length) {
      const found = findCategoryByName(node.children, name);
      if (found) return found;
    }
  }
  return looseMatch;
}

function resolveCategoryRecommendation(
  nodes: CategoryOption[],
  code: string,
  name: string,
): CategoryOption | null {
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

function normalizeCategoryCode(code: string): string {
  return code.trim().toUpperCase().replace(/\s+/g, '');
}

function normalizeCategoryName(name: string): string {
  return name
    .trim()
    .replace(/[（）()《》\s]/g, '')
    .replace(/类$/, '');
}

function getCategoryFallbackCodes(code: string): string[] {
  const normalized = normalizeCategoryCode(code);
  if (!normalized) return [];

  const fallbacks: string[] = [];
  const add = (candidate: string) => {
    if (candidate && candidate !== normalized && !fallbacks.includes(candidate)) {
      fallbacks.push(candidate);
    }
  };

  if (normalized.includes('.')) {
    add(normalized.split('.')[0]);
  }

  const letter = normalized.match(/^[A-Z]+/)?.[0] || '';
  const rest = normalized.slice(letter.length).replace(/[^0-9]/g, '');
  if (!letter || !rest) return fallbacks;

  for (let len = rest.length - 1; len >= 1; len--) {
    add(`${letter}${rest.slice(0, len)}`);
  }
  add(letter);
  return fallbacks;
}

function getErrorMessage(err: unknown): string {
  const axiosError = err as AxiosError<{ detail?: unknown; message?: string }>;
  if (axiosError.response?.data) {
    const { detail, message } = axiosError.response.data;
    if (typeof message === 'string' && message) return message;
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (!item || typeof item !== 'object') return '';
          const record = item as { loc?: unknown[]; msg?: string };
          const field = Array.isArray(record.loc) ? record.loc.filter((part) => part !== 'body').join('.') : '';
          return field && record.msg ? `${field}: ${record.msg}` : record.msg || '';
        })
        .filter(Boolean)
        .join('；');
    }
  }
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
        <p>通过 ISBN、书名+作者或书名+出版社检索图书信息，支持多数据源补全与 AI 推荐</p>
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
        <el-radio-group v-model="activeSearchSource" class="source-filter">
          <el-radio-button
            v-for="tab in sourceTabs"
            :key="tab.source"
            :value="tab.source"
          >
            {{ tab.label }}（{{ tab.count }}）
          </el-radio-button>
        </el-radio-group>
        <div class="results-list">
          <SearchResultCard
            v-for="(result, index) in displayedSearchResults"
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
                :loading="enhanceSearching"
                @click="handleExternalEnhance"
              >
                从其他补全信息
              </el-button>
            </div>
          </el-card>

          <!-- External enhance dialog -->
          <el-dialog
            v-model="enhanceDialogVisible"
            title="从其他数据源补全书目信息"
            width="560px"
            append-to-body
          >
            <div v-if="enhanceSearching" class="enhance-loading">
              <el-skeleton v-for="i in 3" :key="i" :rows="2" animated />
            </div>
            <div v-else-if="enhanceError" class="enhance-error">
              <el-alert :title="enhanceError" :closable="false" type="warning" show-icon />
            </div>
            <div v-else class="enhance-results">
              <p class="enhance-hint">选择一个数据源版本，仅补充当前为空的字段。可重复打开并选择其他数据源累计补全。</p>
              <div class="results-list">
                <SearchResultCard
                  v-for="(result, index) in enhanceResults"
                  :key="index"
                  :result="result"
                  @select="handleApplyEnhanceResult"
                />
              </div>
            </div>
            <template #footer>
              <el-button @click="enhanceDialogVisible = false">取消</el-button>
            </template>
          </el-dialog>

          <!-- AI model selector -->
          <el-card v-if="aiAvailable && aiModels.length > 0" class="ai-model-card">
            <template #header>AI 设置</template>
            <el-select v-model="selectedModel" placeholder="选择模型" size="small" style="width: 100%">
              <el-option
                v-for="model in aiModelOptions"
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

          <!-- Content recommendation -->
          <AIRecommendationCard
            title="AI 检索内容推荐"
            :status="!aiAvailable ? 'unavailable' : (contentDismissed ? 'idle' : contentStatus)"
            :error-message="contentError"
            @accept="handleAcceptContentRecommendation"
            @dismiss="handleDismissContentRecommendation"
            @retry="handleGenerateContentRecommendation"
          >
            <template #idle>
              <div v-if="!contentDismissed" class="ai-idle-content">
                <p>先检索外部数据源，再由 AI 整理当前空字段的推荐内容</p>
                <el-button
                  :disabled="!aiAvailable"
                  :loading="getAIButtonStatus(contentStatus)"
                  size="small"
                  type="primary"
                  @click="handleGenerateContentRecommendation"
                >
                  生成内容推荐
                </el-button>
              </div>
              <div v-else class="ai-done-content">
                <el-text type="success" size="small">已处理内容推荐</el-text>
              </div>
            </template>

            <div v-if="contentResult" class="content-result">
              <div class="result-row">
                <span class="result-label">置信度</span>
                <el-progress
                  :percentage="Math.round(contentResult.confidence * 100)"
                  :stroke-width="8"
                  style="width: 120px"
                />
              </div>
              <div class="content-fields">
                <div
                  v-for="item in getRecommendedContentEntries()"
                  :key="item.label"
                  class="content-field"
                >
                  <span class="result-label">{{ item.label }}</span>
                  <span>{{ item.value }}</span>
                </div>
              </div>
              <div v-if="contentResult.sourceSummary" class="result-reason">
                {{ contentResult.sourceSummary }}
              </div>
              <div v-if="contentResult.reason" class="result-reason">
                {{ contentResult.reason }}
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

.source-filter {
  align-self: flex-start;
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

.enhance-loading {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.enhance-hint {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.enhance-results {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.enhance-error {
  padding: 8px 0;
}

/* AI results */
.classify-result,
.content-result {
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

.content-fields {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.content-field {
  display: grid;
  gap: 4px;
  padding: 6px 8px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
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
