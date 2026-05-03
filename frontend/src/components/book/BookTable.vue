<script setup lang="ts">
import { Delete, Edit, View } from '@element-plus/icons-vue';

import type { BookListItem } from '@/types/book';
import {
  getBookStatusLabel,
  getBookStatusTagType,
  getReadStatusLabel,
  getReadStatusTagType,
} from './bookLabels';

defineProps<{
  books: BookListItem[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  view: [book: BookListItem];
  edit: [book: BookListItem];
  delete: [book: BookListItem];
}>();

function formatDate(value: string) {
  return value ? new Date(value).toLocaleDateString('zh-CN') : '-';
}
</script>

<template>
  <el-table v-loading="loading" :data="books" row-key="id" class="book-table">
    <el-table-column label="封面" width="88">
      <template #default="{ row }">
        <el-image v-if="row.coverUrl" :src="row.coverUrl" fit="cover" class="book-cover" />
        <div v-else class="book-cover-placeholder">书</div>
      </template>
    </el-table-column>

    <el-table-column label="书名" min-width="220">
      <template #default="{ row }">
        <button class="link-button book-title" type="button" @click="emit('view', row)">
          {{ row.title }}
        </button>
        <div v-if="row.subtitle" class="muted-text">{{ row.subtitle }}</div>
        <div class="muted-text">{{ row.isbn || '无 ISBN' }}</div>
      </template>
    </el-table-column>

    <el-table-column label="作者" prop="author" min-width="120" show-overflow-tooltip />
    <el-table-column label="出版社" prop="publisher" min-width="150" show-overflow-tooltip />

    <el-table-column label="分类" min-width="130">
      <template #default="{ row }">
        <span>{{ row.category ? `${row.category.code} ${row.category.name}` : '-' }}</span>
      </template>
    </el-table-column>

    <el-table-column label="位置" min-width="180" show-overflow-tooltip>
      <template #default="{ row }">
        <span>{{ row.location?.fullPath || '-' }}</span>
      </template>
    </el-table-column>

    <el-table-column label="状态" width="98">
      <template #default="{ row }">
        <el-tag :type="getBookStatusTagType(row.status)" effect="light">
          {{ getBookStatusLabel(row.status) }}
        </el-tag>
      </template>
    </el-table-column>

    <el-table-column label="阅读" width="98">
      <template #default="{ row }">
        <el-tag :type="getReadStatusTagType(row.readStatus)" effect="light">
          {{ getReadStatusLabel(row.readStatus) }}
        </el-tag>
      </template>
    </el-table-column>

    <el-table-column label="评分" width="120">
      <template #default="{ row }">
        <el-rate :model-value="row.rating || 0" disabled size="small" />
      </template>
    </el-table-column>

    <el-table-column label="更新时间" width="120">
      <template #default="{ row }">
        {{ formatDate(row.updatedAt) }}
      </template>
    </el-table-column>

    <el-table-column fixed="right" label="操作" width="150">
      <template #default="{ row }">
        <el-button :icon="View" text type="primary" @click="emit('view', row)" />
        <el-button :icon="Edit" text type="primary" @click="emit('edit', row)" />
        <el-button :icon="Delete" text type="danger" @click="emit('delete', row)" />
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.book-table {
  border: 1px solid var(--app-border);
  border-radius: 8px;
}

.book-cover,
.book-cover-placeholder {
  width: 48px;
  height: 64px;
  border-radius: 4px;
}

.book-cover-placeholder {
  display: grid;
  place-items: center;
  background: #eef3f1;
  color: var(--app-muted);
}

.link-button {
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--el-color-primary);
  cursor: pointer;
  font: inherit;
}

.book-title {
  font-weight: 700;
}

.muted-text {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
}
</style>
