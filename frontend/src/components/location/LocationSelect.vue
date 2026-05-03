<script setup lang="ts">
import { ElMessage } from 'element-plus';
import { computed, onMounted, ref } from 'vue';

import { fetchLocations } from '@/api/locations';
import type { Location } from '@/types/location';

const props = withDefaults(
  defineProps<{
    modelValue?: number | null;
    placeholder?: string;
    clearable?: boolean;
    disabled?: boolean;
  }>(),
  {
    modelValue: null,
    placeholder: '请选择位置',
    clearable: true,
    disabled: false,
  },
);

const emit = defineEmits<{
  (e: 'update:modelValue', value: number | null): void;
  (e: 'change', value: number | null): void;
}>();

const loading = ref(false);
const locations = ref<Location[]>([]);

const groupedOptions = computed(() => {
  const map = new Map<string, Location[]>();
  for (const loc of locations.value) {
    if (!map.has(loc.room)) map.set(loc.room, []);
    map.get(loc.room)!.push(loc);
  }
  return map;
});

async function load() {
  if (locations.value.length > 0) return;
  loading.value = true;
  try {
    locations.value = await fetchLocations();
  } catch {
    ElMessage.error('加载位置失败');
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function handleChange(value: number | null) {
  emit('update:modelValue', value);
  emit('change', value);
}
</script>

<template>
  <el-select
    :model-value="props.modelValue"
    :placeholder="props.placeholder"
    :clearable="props.clearable"
    :disabled="props.disabled || loading"
    :loading="loading"
    filterable
    @update:model-value="handleChange"
  >
    <el-option-group v-for="[room, locs] of groupedOptions" :key="room" :label="room">
      <el-option
        v-for="loc in locs"
        :key="loc.id"
        :value="loc.id"
        :label="loc.fullPath"
      />
    </el-option-group>
  </el-select>
</template>
