<script setup lang="ts">
import { Picture } from '@element-plus/icons-vue';

import type { SearchResultItem } from '@/types/search';

defineProps<{
  result: SearchResultItem;
  selected?: boolean;
}>();

const emit = defineEmits<{
  select: [result: SearchResultItem];
}>();

const SOURCE_LABELS: Record<string, string> = {
  open_library: 'Open Library',
  google_books: 'Google Books',
  isbn_db: 'ISBN DB',
  douban: '豆瓣读书',
};

function getSourceLabel(source: string): string {
  return SOURCE_LABELS[source] || source;
}
</script>

<template>
  <el-card
    class="search-result-card"
    :class="{ 'is-selected': selected }"
    shadow="hover"
    @click="emit('select', result)"
  >
    <div class="card-inner">
      <div class="cover-area">
        <el-image
          v-if="result.coverUrl"
          :src="result.coverUrl"
          class="book-cover"
          fit="cover"
        >
          <template #error>
            <div class="cover-placeholder">
              <el-icon :size="28"><Picture /></el-icon>
            </div>
          </template>
        </el-image>
        <div v-else class="cover-placeholder">
          <el-icon :size="28"><Picture /></el-icon>
        </div>
      </div>

      <div class="book-info">
        <div class="book-title" :title="result.title">{{ result.title }}</div>
        <div v-if="result.subtitle" class="book-subtitle">{{ result.subtitle }}</div>

        <div class="book-meta">
          <span v-if="result.author" class="meta-item">
            <span class="meta-label">作者：</span>{{ result.author }}
          </span>
          <span v-if="result.publisher" class="meta-item">
            <span class="meta-label">出版社：</span>{{ result.publisher }}
          </span>
          <span v-if="result.publishYear" class="meta-item">
            <span class="meta-label">年份：</span>{{ result.publishYear }}
          </span>
          <span v-if="result.isbn" class="meta-item">
            <span class="meta-label">ISBN：</span>{{ result.isbn }}
          </span>
        </div>

        <div v-if="result.summary" class="book-summary">{{ result.summary }}</div>

        <div class="card-footer">
          <el-tag size="small" type="info">{{ getSourceLabel(result.source) }}</el-tag>
          <el-button
            size="small"
            type="primary"
            @click.stop="emit('select', result)"
          >
            选择此版本
          </el-button>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.search-result-card {
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.search-result-card:hover {
  border-color: var(--el-color-primary-light-3);
}

.search-result-card.is-selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-5);
}

.card-inner {
  display: flex;
  gap: 14px;
}

.cover-area {
  flex-shrink: 0;
  width: 72px;
}

.book-cover {
  width: 72px;
  height: 96px;
  border-radius: 4px;
  object-fit: cover;
}

.cover-placeholder {
  width: 72px;
  height: 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color);
  border-radius: 4px;
  color: var(--el-text-color-placeholder);
}

.book-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.book-title {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.book-subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.book-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.meta-label {
  color: var(--el-text-color-placeholder);
}

.book-summary {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 6px;
}
</style>
