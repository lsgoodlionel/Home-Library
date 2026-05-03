<script setup lang="ts">
import { RefreshRight, View } from '@element-plus/icons-vue';

import type { BorrowRecord } from '@/types/borrow';
import { isBorrowOverdue } from '@/types/borrow';

defineProps<{
  records: BorrowRecord[];
  loading?: boolean;
  showReturn?: boolean;
}>();

const emit = defineEmits<{
  return: [record: BorrowRecord];
  viewBook: [bookId: number];
}>();

function formatDate(value: string | null) {
  return value || '-';
}
</script>

<template>
  <el-table v-loading="loading" :data="records" row-key="id" class="borrow-table">
    <el-table-column label="图书" min-width="220">
      <template #default="{ row }">
        <button class="link-button" type="button" @click="emit('viewBook', row.bookId)">
          {{ row.book?.title || `图书 #${row.bookId}` }}
        </button>
        <div class="muted-text">{{ row.book?.author || '' }}</div>
      </template>
    </el-table-column>
    <el-table-column label="借阅人" prop="borrowerName" width="130" />
    <el-table-column label="联系方式" prop="borrowerContact" min-width="150" show-overflow-tooltip />
    <el-table-column label="借出日期" width="120">
      <template #default="{ row }">{{ formatDate(row.borrowedAt) }}</template>
    </el-table-column>
    <el-table-column label="应还日期" width="120">
      <template #default="{ row }">
        <el-tag v-if="isBorrowOverdue(row)" type="danger" effect="light">{{ row.dueAt }}</el-tag>
        <span v-else>{{ formatDate(row.dueAt) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="归还日期" width="120">
      <template #default="{ row }">{{ formatDate(row.returnedAt) }}</template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }">
        <el-tag v-if="row.returnedAt || row.status === 'returned'" type="success">已归还</el-tag>
        <el-tag v-else-if="isBorrowOverdue(row)" type="danger">超期</el-tag>
        <el-tag v-else type="warning">借出中</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="备注" prop="note" min-width="160" show-overflow-tooltip />
    <el-table-column fixed="right" label="操作" width="120">
      <template #default="{ row }">
        <el-button :icon="View" text type="primary" @click="emit('viewBook', row.bookId)" />
        <el-button
          v-if="showReturn && !row.returnedAt && row.status !== 'returned'"
          :icon="RefreshRight"
          text
          type="primary"
          @click="emit('return', row)"
        />
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.borrow-table {
  border: 1px solid var(--app-border);
  border-radius: 8px;
}

.link-button {
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--el-color-primary);
  cursor: pointer;
  font: inherit;
  font-weight: 700;
}

.muted-text {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
}
</style>
