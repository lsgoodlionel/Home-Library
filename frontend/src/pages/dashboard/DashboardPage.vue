<script setup lang="ts">
import { Collection, DataAnalysis, Plus, Search } from '@element-plus/icons-vue';
import { computed, onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

import { getStatsOverview } from '@/api/stats';
import ChartCard from '@/components/charts/ChartCard.vue';
import type { StatsOverview } from '@/types/stats';

const overview = ref<StatsOverview | null>(null);
const loading = ref(false);
const error = ref('');

const metrics = computed(() => [
  { label: '总藏书数', value: overview.value?.totalBooks ?? 0, tone: 'primary' },
  { label: '在架数量', value: overview.value?.availableBooks ?? 0, tone: 'green' },
  { label: '借出数量', value: overview.value?.borrowedBooks ?? 0, tone: 'amber' },
  { label: '已读数量', value: overview.value?.readBooks ?? 0, tone: 'blue' },
]);

function formatDate(value: string) {
  if (!value) {
    return '未记录';
  }
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(
    new Date(value),
  );
}

async function loadOverview() {
  loading.value = true;
  error.value = '';

  try {
    overview.value = await getStatsOverview();
  } catch {
    error.value = '统计接口暂不可用，请确认后端 /api/stats/overview 已启动。';
  } finally {
    loading.value = false;
  }
}

onMounted(loadOverview);
</script>

<template>
  <section class="dashboard-page">
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <div class="metric-grid" v-loading="loading">
      <div v-for="metric in metrics" :key="metric.label" class="metric-card" :class="`metric-card--${metric.tone}`">
        <div class="metric-label">{{ metric.label }}</div>
        <div class="metric-value">{{ metric.value }}</div>
      </div>
    </div>

    <div class="dashboard-grid">
      <ChartCard
        title="最近入库"
        subtitle="按入库时间展示最新图书"
        :loading="loading"
        :empty="!loading && !overview?.recentBooks.length"
        empty-text="暂无最近入库记录"
      >
        <div class="book-list">
          <RouterLink
            v-for="book in overview?.recentBooks"
            :key="book.id || book.title"
            class="book-list__item"
            :to="book.id ? `/books/${book.id}` : '/books'"
          >
            <div>
              <strong>{{ book.title }}</strong>
              <span>{{ book.author || '作者未记录' }}</span>
            </div>
            <small>{{ formatDate(book.createdAt) }}</small>
          </RouterLink>
        </div>
      </ChartCard>

      <ChartCard
        title="当前借出"
        subtitle="尚未归还的借阅记录"
        :loading="loading"
        :empty="!loading && !overview?.activeBorrows.length"
        empty-text="暂无当前借出记录"
      >
        <div class="borrow-list">
          <div v-for="record in overview?.activeBorrows" :key="record.id || record.bookTitle" class="borrow-list__item">
            <div>
              <strong>{{ record.bookTitle }}</strong>
              <span>{{ record.borrowerName || '借阅人未记录' }}</span>
            </div>
            <small>借出 {{ formatDate(record.borrowedAt) }}</small>
          </div>
        </div>
      </ChartCard>
    </div>

    <ChartCard title="快速入口" subtitle="常用工作流">
      <div class="quick-actions">
        <RouterLink class="quick-action" to="/books/new">
          <el-icon><Plus /></el-icon>
          <span>新增图书</span>
        </RouterLink>
        <RouterLink class="quick-action" to="/books">
          <el-icon><Search /></el-icon>
          <span>检索藏书</span>
        </RouterLink>
        <RouterLink class="quick-action" to="/smart-import">
          <el-icon><Collection /></el-icon>
          <span>智能入库</span>
        </RouterLink>
        <RouterLink class="quick-action" to="/stats">
          <el-icon><DataAnalysis /></el-icon>
          <span>统计分析</span>
        </RouterLink>
      </div>
    </ChartCard>
  </section>
</template>

<style scoped>
.dashboard-page {
  display: grid;
  gap: 20px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.metric-card {
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: #ffffff;
}

.metric-card--primary {
  border-top: 3px solid #2f6f73;
}

.metric-card--green {
  border-top: 3px solid #5b8c65;
}

.metric-card--amber {
  border-top: 3px solid #b57a36;
}

.metric-card--blue {
  border-top: 3px solid #4c78a8;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.book-list,
.borrow-list {
  display: grid;
  gap: 10px;
}

.book-list__item,
.borrow-list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  min-width: 0;
  padding: 12px;
  border: 1px solid #edf0f2;
  border-radius: 8px;
}

.book-list__item div,
.borrow-list__item div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.book-list__item strong,
.borrow-list__item strong,
.book-list__item span,
.borrow-list__item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.book-list__item span,
.borrow-list__item span,
.book-list__item small,
.borrow-list__item small {
  color: var(--app-muted);
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.quick-action {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 48px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: #f9fbfb;
  color: var(--app-text);
  font-weight: 600;
}

@media (max-width: 1024px) {
  .metric-grid,
  .dashboard-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .metric-grid,
  .dashboard-grid,
  .quick-actions {
    grid-template-columns: 1fr;
  }

  .book-list__item,
  .borrow-list__item {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
