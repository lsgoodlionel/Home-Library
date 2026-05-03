<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  items: Array<{ period: string; count: number }>;
}>();

const width = 640;
const height = 220;
const padding = 28;

const maxCount = computed(() => Math.max(1, ...props.items.map((item) => item.count)));
const points = computed(() =>
  props.items.map((item, index) => {
    const x =
      props.items.length === 1
        ? width / 2
        : padding + (index / (props.items.length - 1)) * (width - padding * 2);
    const y = height - padding - (item.count / maxCount.value) * (height - padding * 2);
    return { ...item, x, y };
  }),
);
const path = computed(() =>
  points.value.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' '),
);
</script>

<template>
  <div class="line-chart">
    <svg :viewBox="`0 0 ${width} ${height}`" role="img" aria-label="趋势图">
      <line :x1="padding" :x2="width - padding" :y1="height - padding" :y2="height - padding" />
      <line :x1="padding" :x2="padding" :y1="padding" :y2="height - padding" />
      <path :d="path" />
      <g v-for="point in points" :key="point.period">
        <circle :cx="point.x" :cy="point.y" r="4" />
        <text :x="point.x" :y="height - 8" text-anchor="middle">{{ point.period }}</text>
        <text :x="point.x" :y="point.y - 10" text-anchor="middle" class="line-chart__value">
          {{ point.count }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.line-chart {
  overflow-x: auto;
  min-width: 0;
}

.line-chart svg {
  display: block;
  min-width: 520px;
  width: 100%;
  height: auto;
}

.line-chart line {
  stroke: #d7dee2;
  stroke-width: 1;
}

.line-chart path {
  fill: none;
  stroke: #2f6f73;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 3;
}

.line-chart circle {
  fill: #ffffff;
  stroke: #2f6f73;
  stroke-width: 3;
}

.line-chart text {
  fill: var(--app-muted);
  font-size: 12px;
}

.line-chart__value {
  fill: var(--app-text);
  font-weight: 700;
}
</style>
