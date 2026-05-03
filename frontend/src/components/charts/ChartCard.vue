<script setup lang="ts">
defineProps<{
  title: string;
  subtitle?: string;
  loading?: boolean;
  error?: string;
  empty?: boolean;
  emptyText?: string;
}>();
</script>

<template>
  <section class="chart-card" v-loading="loading">
    <header class="chart-card__header">
      <div>
        <h2>{{ title }}</h2>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
      <slot name="actions" />
    </header>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-empty v-else-if="empty" :description="emptyText || '暂无统计数据'" />
    <div v-else class="chart-card__body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.chart-card {
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: #ffffff;
}

.chart-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.chart-card h2 {
  margin: 0;
  color: var(--app-text);
  font-size: 16px;
}

.chart-card p {
  margin: 4px 0 0;
  color: var(--app-muted);
  font-size: 13px;
}

.chart-card__body {
  min-width: 0;
}
</style>
