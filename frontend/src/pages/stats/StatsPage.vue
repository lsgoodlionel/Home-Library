<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import {
  getCategoryStats,
  getLocationStats,
  getReadingStats,
  getTimelineStats,
} from '@/api/stats';
import BarChart from '@/components/charts/BarChart.vue';
import ChartCard from '@/components/charts/ChartCard.vue';
import LineChart from '@/components/charts/LineChart.vue';
import PieChart from '@/components/charts/PieChart.vue';
import type { DistributionItem, ReadingStats, TimelinePoint } from '@/types/stats';

const categoryItems = ref<DistributionItem[]>([]);
const locationItems = ref<DistributionItem[]>([]);
const readingStats = ref<ReadingStats | null>(null);
const timelineItems = ref<TimelinePoint[]>([]);

const loading = ref({
  categories: false,
  locations: false,
  reading: false,
  timeline: false,
});

const errors = ref({
  categories: '',
  locations: '',
  reading: '',
  timeline: '',
});

const readingItems = computed(() => [
  { name: '未读', count: readingStats.value?.unread || 0, color: '#6b7280' },
  { name: '阅读中', count: readingStats.value?.reading || 0, color: '#4c78a8' },
  { name: '已读', count: readingStats.value?.read || 0, color: '#2f6f73' },
  { name: '暂停', count: readingStats.value?.paused || 0, color: '#b57a36' },
]);

function hasValues(items: Array<{ count: number }>) {
  return items.some((item) => item.count > 0);
}

async function loadCategories() {
  loading.value.categories = true;
  errors.value.categories = '';
  try {
    categoryItems.value = await getCategoryStats();
  } catch {
    errors.value.categories = '分类统计接口暂不可用。';
  } finally {
    loading.value.categories = false;
  }
}

async function loadLocations() {
  loading.value.locations = true;
  errors.value.locations = '';
  try {
    locationItems.value = await getLocationStats();
  } catch {
    errors.value.locations = '位置统计接口暂不可用。';
  } finally {
    loading.value.locations = false;
  }
}

async function loadReading() {
  loading.value.reading = true;
  errors.value.reading = '';
  try {
    readingStats.value = await getReadingStats();
  } catch {
    errors.value.reading = '阅读状态统计接口暂不可用。';
  } finally {
    loading.value.reading = false;
  }
}

async function loadTimeline() {
  loading.value.timeline = true;
  errors.value.timeline = '';
  try {
    timelineItems.value = await getTimelineStats();
  } catch {
    errors.value.timeline = '趋势统计接口暂不可用。';
  } finally {
    loading.value.timeline = false;
  }
}

onMounted(() => {
  void loadCategories();
  void loadLocations();
  void loadReading();
  void loadTimeline();
});
</script>

<template>
  <section class="stats-page">
    <div class="stats-page__header">
      <div>
        <h1>统计分析</h1>
        <p>查看藏书分布、阅读状态和入库趋势。</p>
      </div>
    </div>

    <div class="stats-grid">
      <ChartCard
        title="分类分布"
        subtitle="按分类汇总藏书数量"
        :loading="loading.categories"
        :error="errors.categories"
        :empty="!loading.categories && !hasValues(categoryItems)"
      >
        <PieChart :items="categoryItems.slice(0, 8)" />
      </ChartCard>

      <ChartCard
        title="位置分布"
        subtitle="按摆放位置汇总藏书数量"
        :loading="loading.locations"
        :error="errors.locations"
        :empty="!loading.locations && !hasValues(locationItems)"
      >
        <BarChart :items="locationItems.slice(0, 8)" />
      </ChartCard>

      <ChartCard
        title="阅读状态"
        subtitle="未读、阅读中、已读和暂停"
        :loading="loading.reading"
        :error="errors.reading"
        :empty="!loading.reading && !hasValues(readingItems)"
      >
        <PieChart :items="readingItems" />
      </ChartCard>

      <ChartCard
        title="入库趋势"
        subtitle="年度或月度新增藏书"
        :loading="loading.timeline"
        :error="errors.timeline"
        :empty="!loading.timeline && !hasValues(timelineItems)"
      >
        <LineChart :items="timelineItems" />
      </ChartCard>

      <ChartCard title="作者排行" subtitle="等待后端统计接口提供作者聚合数据" empty empty-text="作者排行接口待接入" />
    </div>
  </section>
</template>

<style scoped>
.stats-page {
  display: grid;
  gap: 20px;
}

.stats-page__header h1 {
  margin: 0;
  font-size: 22px;
}

.stats-page__header p {
  margin: 6px 0 0;
  color: var(--app-muted);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

@media (max-width: 960px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
