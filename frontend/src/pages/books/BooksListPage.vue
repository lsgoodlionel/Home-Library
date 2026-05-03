<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import {
  deleteBook,
  getBooks,
  getCategoryOptions,
  getLocationOptions,
} from '@/api/books';
import BookCardList from '@/components/book/BookCardList.vue';
import BookFilters from '@/components/book/BookFilters.vue';
import BookTable from '@/components/book/BookTable.vue';
import type { BookListItem, BookQuery, CategoryOption, LocationOption } from '@/types/book';

const router = useRouter();

const loading = ref(false);
const optionsLoading = ref(false);
const viewMode = ref<'table' | 'card'>('table');
const books = ref<BookListItem[]>([]);
const total = ref(0);
const categories = ref<CategoryOption[]>([]);
const locations = ref<LocationOption[]>([]);

const query = ref<BookQuery>({
  page: 1,
  pageSize: 20,
  keyword: '',
  categoryId: undefined,
  locationId: undefined,
  status: undefined,
  readStatus: undefined,
  isFavorite: undefined,
});

async function loadOptions() {
  optionsLoading.value = true;

  try {
    const [categoryData, locationData] = await Promise.all([
      getCategoryOptions(),
      getLocationOptions(),
    ]);
    categories.value = categoryData;
    locations.value = locationData;
  } catch {
    ElMessage.error('分类或位置选项加载失败');
  } finally {
    optionsLoading.value = false;
  }
}

async function loadBooks() {
  loading.value = true;

  try {
    const data = await getBooks(query.value);
    books.value = data.items;
    total.value = data.total;
  } catch {
    ElMessage.error('图书列表加载失败');
    books.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  query.value.page = 1;
  void loadBooks();
}

function handleReset() {
  query.value.page = 1;
  query.value.keyword = '';
  query.value.categoryId = undefined;
  query.value.locationId = undefined;
  query.value.status = undefined;
  query.value.readStatus = undefined;
  query.value.isFavorite = undefined;
  void loadBooks();
}

function handlePageChange(page: number) {
  query.value.page = page;
  void loadBooks();
}

function handlePageSizeChange(pageSize: number) {
  query.value.pageSize = pageSize;
  query.value.page = 1;
  void loadBooks();
}

function viewBook(book: BookListItem) {
  void router.push({ name: 'book-detail', params: { id: book.id } });
}

function editBook(book: BookListItem) {
  void router.push({ name: 'book-edit', params: { id: book.id } });
}

async function handleDelete(book: BookListItem) {
  try {
    await ElMessageBox.confirm(`确认删除《${book.title}》吗？此操作不可撤销。`, '删除图书', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
    await deleteBook(book.id);
    ElMessage.success('图书已删除');
    await loadBooks();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败，请稍后重试');
    }
  }
}

onMounted(() => {
  void loadOptions();
  void loadBooks();
});
</script>

<template>
  <section class="books-page">
    <div class="page-toolbar">
      <div>
        <h1>藏书</h1>
        <p>检索、筛选和维护家庭藏书记录</p>
      </div>
      <div class="toolbar-actions">
        <el-segmented v-model="viewMode" :options="[
          { label: '表格', value: 'table' },
          { label: '卡片', value: 'card' },
        ]" />
        <el-button :icon="Plus" type="primary" @click="router.push({ name: 'book-new' })">
          新增图书
        </el-button>
      </div>
    </div>

    <BookFilters
      v-model="query"
      :categories="categories"
      :loading="loading || optionsLoading"
      :locations="locations"
      @reset="handleReset"
      @search="handleSearch"
    />

    <div class="book-list-panel">
      <BookTable
        v-if="viewMode === 'table'"
        :books="books"
        :loading="loading"
        @delete="handleDelete"
        @edit="editBook"
        @view="viewBook"
      />
      <BookCardList
        v-else
        :books="books"
        @delete="handleDelete"
        @edit="editBook"
        @view="viewBook"
      />

      <el-empty v-if="!loading && books.length === 0" description="暂无符合条件的图书" />

      <div class="pagination-row">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          background
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.books-page {
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
  color: var(--app-muted);
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.book-list-panel {
  display: grid;
  gap: 14px;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .page-toolbar,
  .toolbar-actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
