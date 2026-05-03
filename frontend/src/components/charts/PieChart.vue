<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  items: Array<{ name: string; count: number; color?: string }>;
}>();

const palette = ['#2f6f73', '#8f6f3f', '#4c78a8', '#d07f4f', '#6b7280', '#7a8f55'];
const total = computed(() => props.items.reduce((sum, item) => sum + item.count, 0));

const segments = computed(() => {
  let offset = 25;
  return props.items.map((item, index) => {
    const dash = total.value > 0 ? (item.count / total.value) * 100 : 0;
    const segment = {
      ...item,
      color: item.color || palette[index % palette.length],
      dash,
      offset,
    };
    offset -= dash;
    return segment;
  });
});
</script>

<template>
  <div class="pie-chart">
    <svg class="pie-chart__svg" viewBox="0 0 42 42" role="img" aria-label="分布图">
      <circle class="pie-chart__base" cx="21" cy="21" r="15.915" />
      <circle
        v-for="segment in segments"
        :key="segment.name"
        class="pie-chart__segment"
        cx="21"
        cy="21"
        r="15.915"
        :stroke="segment.color"
        :stroke-dasharray="`${segment.dash} ${100 - segment.dash}`"
        :stroke-dashoffset="segment.offset"
      />
      <text x="21" y="19.5" text-anchor="middle" class="pie-chart__total">{{ total }}</text>
      <text x="21" y="24.5" text-anchor="middle" class="pie-chart__caption">册</text>
    </svg>

    <div class="pie-chart__legend">
      <div v-for="segment in segments" :key="segment.name" class="pie-chart__legend-item">
        <span class="pie-chart__dot" :style="{ background: segment.color }" />
        <span class="pie-chart__name" :title="segment.name">{{ segment.name }}</span>
        <span class="pie-chart__count">{{ segment.count }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pie-chart {
  display: grid;
  grid-template-columns: minmax(150px, 190px) minmax(0, 1fr);
  align-items: center;
  gap: 20px;
}

.pie-chart__svg {
  width: 100%;
  max-width: 190px;
  aspect-ratio: 1;
}

.pie-chart__base {
  fill: none;
  stroke: #edf2f4;
  stroke-width: 8;
}

.pie-chart__segment {
  fill: none;
  stroke-width: 8;
  transform: rotate(-90deg);
  transform-origin: center;
}

.pie-chart__total {
  fill: var(--app-text);
  font-size: 7px;
  font-weight: 700;
}

.pie-chart__caption {
  fill: var(--app-muted);
  font-size: 3px;
}

.pie-chart__legend {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.pie-chart__legend-item {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) 40px;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.pie-chart__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.pie-chart__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pie-chart__count {
  color: var(--app-muted);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

@media (max-width: 640px) {
  .pie-chart {
    grid-template-columns: 1fr;
  }

  .pie-chart__svg {
    justify-self: center;
  }
}
</style>
