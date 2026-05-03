<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  items: Array<{ name: string; count: number }>;
  compact?: boolean;
}>();

const maxCount = computed(() => Math.max(1, ...props.items.map((item) => item.count)));
</script>

<template>
  <div class="bar-chart" :class="{ 'bar-chart--compact': compact }">
    <div v-for="item in items" :key="item.name" class="bar-row">
      <div class="bar-row__label" :title="item.name">{{ item.name }}</div>
      <div class="bar-row__track">
        <div class="bar-row__value" :style="{ width: `${Math.max(4, (item.count / maxCount) * 100)}%` }" />
      </div>
      <div class="bar-row__count">{{ item.count }}</div>
    </div>
  </div>
</template>

<style scoped>
.bar-chart {
  display: grid;
  gap: 12px;
}

.bar-row {
  display: grid;
  grid-template-columns: minmax(88px, 140px) minmax(90px, 1fr) 42px;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.bar-row__label {
  overflow: hidden;
  color: var(--app-text);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-row__track {
  overflow: hidden;
  height: 10px;
  border-radius: 999px;
  background: #edf2f4;
}

.bar-row__value {
  height: 100%;
  border-radius: inherit;
  background: #2f6f73;
}

.bar-row__count {
  color: var(--app-muted);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.bar-chart--compact .bar-row {
  grid-template-columns: minmax(72px, 110px) minmax(80px, 1fr) 36px;
}

@media (max-width: 640px) {
  .bar-row {
    grid-template-columns: 1fr 40px;
    gap: 8px;
  }

  .bar-row__label {
    grid-column: 1 / -1;
  }
}
</style>
