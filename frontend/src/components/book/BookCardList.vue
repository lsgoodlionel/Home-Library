<script setup lang="ts">
import { Delete, Edit, View } from '@element-plus/icons-vue';

import type { BookListItem } from '@/types/book';
import { bookStatusLabel, bookStatusTagType, readStatusLabel } from './bookLabels';

defineProps<{
  books: BookListItem[];
}>();

const emit = defineEmits<{
  view: [book: BookListItem];
  edit: [book: BookListItem];
  delete: [book: BookListItem];
}>();
</script>

<template>
  <div class="book-card-list">
    <article v-for="book in books" :key="book.id" class="book-card">
      <el-image v-if="book.coverUrl" :src="book.coverUrl" fit="cover" class="book-card-cover" />
      <div v-else class="book-card-cover book-card-cover-empty">书</div>

      <div class="book-card-body">
        <div class="book-card-title">{{ book.title }}</div>
        <div class="book-card-meta">{{ book.author || '作者未录入' }}</div>
        <div class="book-card-meta">{{ book.location?.fullPath || '位置未设置' }}</div>
        <div class="book-card-tags">
          <el-tag :type="bookStatusTagType[book.status]" effect="light">
            {{ bookStatusLabel[book.status] }}
          </el-tag>
          <el-tag effect="plain">{{ readStatusLabel[book.readStatus] }}</el-tag>
        </div>
      </div>

      <div class="book-card-actions">
        <el-button :icon="View" text type="primary" @click="emit('view', book)" />
        <el-button :icon="Edit" text type="primary" @click="emit('edit', book)" />
        <el-button :icon="Delete" text type="danger" @click="emit('delete', book)" />
      </div>
    </article>
  </div>
</template>

<style scoped>
.book-card-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.book-card {
  display: grid;
  grid-template-columns: 64px 1fr auto;
  gap: 12px;
  align-items: start;
  padding: 14px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: #ffffff;
}

.book-card-cover {
  width: 64px;
  height: 88px;
  border-radius: 4px;
}

.book-card-cover-empty {
  display: grid;
  place-items: center;
  background: #eef3f1;
  color: var(--app-muted);
}

.book-card-title {
  font-weight: 700;
}

.book-card-meta {
  margin-top: 6px;
  color: var(--app-muted);
  font-size: 13px;
}

.book-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.book-card-actions {
  display: flex;
  flex-direction: column;
}
</style>
