<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { createBorrow, getActiveBorrows, getBorrowRecords, returnBorrow } from '@/api/borrow';
import { getBooks } from '@/api/books';
import BorrowDialog from '@/components/borrow/BorrowDialog.vue';
import BorrowTable from '@/components/borrow/BorrowTable.vue';
import ReturnDialog from '@/components/borrow/ReturnDialog.vue';
import type { BookListItem } from '@/types/book';
import type { BorrowCreatePayload, BorrowRecord, BorrowReturnPayload } from '@/types/borrow';

const router = useRouter();

const loading = ref(false);
const saving = ref(false);
const borrowDialogVisible = ref(false);
const returnDialogVisible = ref(false);
const activeRecords = ref<BorrowRecord[]>([]);
const historyRecords = ref<BorrowRecord[]>([]);
const books = ref<BookListItem[]>([]);
const currentReturnRecord = ref<BorrowRecord | null>(null);

async function loadBooks() {
  try {
    const data = await getBooks({ page: 1, pageSize: 100 });
    books.value = data.items;
  } catch {
    ElMessage.error('图书选项加载失败，借出操作可能不可用');
  }
}

async function loadBorrows() {
  loading.value = true;

  try {
    const [active, history] = await Promise.all([getActiveBorrows(), getBorrowRecords()]);
    activeRecords.value = active;
    historyRecords.value = history;
  } catch {
    ElMessage.error('借阅记录加载失败，请确认后端借阅接口可用');
    activeRecords.value = [];
    historyRecords.value = [];
  } finally {
    loading.value = false;
  }
}

async function handleBorrow(payload: BorrowCreatePayload) {
  saving.value = true;

  try {
    await createBorrow(payload);
    ElMessage.success('图书已借出');
    borrowDialogVisible.value = false;
    await loadBorrows();
  } catch {
    ElMessage.error('借出失败，请检查接口或表单内容');
  } finally {
    saving.value = false;
  }
}

function openReturn(record: BorrowRecord) {
  currentReturnRecord.value = record;
  returnDialogVisible.value = true;
}

async function handleReturn(id: number, payload: BorrowReturnPayload) {
  saving.value = true;

  try {
    await returnBorrow(id, payload);
    ElMessage.success('图书已归还');
    returnDialogVisible.value = false;
    await loadBorrows();
  } catch {
    ElMessage.error('归还失败，请稍后重试');
  } finally {
    saving.value = false;
  }
}

function viewBook(bookId: number) {
  void router.push({ name: 'book-detail', params: { id: bookId } });
}

onMounted(() => {
  void loadBooks();
  void loadBorrows();
});
</script>

<template>
  <section class="borrow-page">
    <div class="page-toolbar">
      <div>
        <h1>借阅管理</h1>
        <p>查看当前借出、借阅历史并处理归还</p>
      </div>
      <el-button :icon="Plus" type="primary" @click="borrowDialogVisible = true">借出图书</el-button>
    </div>

    <el-tabs>
      <el-tab-pane label="当前借出">
        <BorrowTable
          :loading="loading"
          :records="activeRecords"
          show-return
          @return="openReturn"
          @view-book="viewBook"
        />
        <el-empty v-if="!loading && activeRecords.length === 0" description="暂无当前借出记录" />
      </el-tab-pane>

      <el-tab-pane label="借阅历史">
        <BorrowTable
          :loading="loading"
          :records="historyRecords"
          @return="openReturn"
          @view-book="viewBook"
        />
        <el-empty v-if="!loading && historyRecords.length === 0" description="暂无借阅历史" />
      </el-tab-pane>
    </el-tabs>

    <BorrowDialog
      v-model="borrowDialogVisible"
      :books="books"
      :loading="saving"
      @submit="handleBorrow"
    />
    <ReturnDialog
      v-model="returnDialogVisible"
      :loading="saving"
      :record="currentReturnRecord"
      @submit="handleReturn"
    />
  </section>
</template>

<style scoped>
.borrow-page {
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
</style>
