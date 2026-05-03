<script setup lang="ts">
import { Delete, Edit, View } from '@element-plus/icons-vue';

import type { ReadingNote } from '@/types/reading';

defineProps<{
  notes: ReadingNote[];
  loading?: boolean;
  showBook?: boolean;
}>();

const emit = defineEmits<{
  edit: [note: ReadingNote];
  delete: [note: ReadingNote];
  viewBook: [bookId: number];
}>();

function formatDate(value: string) {
  return value ? new Date(value).toLocaleDateString('zh-CN') : '-';
}
</script>

<template>
  <div v-loading="loading" class="notes-list">
    <article v-for="note in notes" :key="note.id" class="note-card">
      <div class="note-card-head">
        <div>
          <h3>{{ note.title }}</h3>
          <button v-if="showBook" class="book-link" type="button" @click="emit('viewBook', note.bookId)">
            {{ note.book?.title || `图书 #${note.bookId}` }}
          </button>
        </div>
        <div class="note-actions">
          <el-button v-if="showBook" :icon="View" text type="primary" @click="emit('viewBook', note.bookId)" />
          <el-button :icon="Edit" text type="primary" @click="emit('edit', note)" />
          <el-button :icon="Delete" text type="danger" @click="emit('delete', note)" />
        </div>
      </div>

      <div class="note-meta">
        <span>进度：{{ note.progress ?? '-' }}%</span>
        <el-rate :model-value="note.rating || 0" disabled size="small" />
        <span>更新：{{ formatDate(note.updatedAt || note.createdAt) }}</span>
      </div>

      <p class="note-content">{{ note.content || '暂无笔记内容。' }}</p>
    </article>

    <el-empty v-if="!loading && notes.length === 0" description="暂无阅读笔记" />
  </div>
</template>

<style scoped>
.notes-list {
  display: grid;
  gap: 12px;
  min-height: 120px;
}

.note-card {
  padding: 16px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: #ffffff;
}

.note-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.note-card h3 {
  margin: 0;
  font-size: 16px;
}

.book-link {
  margin-top: 6px;
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--el-color-primary);
  cursor: pointer;
  font: inherit;
}

.note-actions,
.note-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.note-meta {
  flex-wrap: wrap;
  margin-top: 10px;
  color: var(--app-muted);
  font-size: 13px;
}

.note-content {
  margin: 12px 0 0;
  color: var(--app-text);
  line-height: 1.7;
  white-space: pre-wrap;
}
</style>
