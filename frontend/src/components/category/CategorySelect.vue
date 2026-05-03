<script setup lang="ts">
import { ElMessage } from 'element-plus';
import { onMounted, ref } from 'vue';

import { fetchCategories } from '@/api/categories';
import type { Category } from '@/types/category';

const props = withDefaults(
  defineProps<{
    modelValue?: number | null;
    placeholder?: string;
    clearable?: boolean;
    disabled?: boolean;
  }>(),
  {
    modelValue: null,
    placeholder: '请选择分类',
    clearable: true,
    disabled: false,
  },
);

const emit = defineEmits<{
  (e: 'update:modelValue', value: number | null): void;
  (e: 'change', value: number | null): void;
}>();

const treeProps = { label: 'name', children: 'children', value: 'id' };

const loading = ref(false);
const treeData = ref<Category[]>([]);

async function load() {
  if (treeData.value.length > 0) return;
  loading.value = true;
  try {
    treeData.value = await fetchCategories();
  } catch {
    ElMessage.error('加载分类失败');
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
  <el-tree-select
    :model-value="props.modelValue"
    :data="treeData"
    :props="treeProps"
    node-key="id"
    :placeholder="props.placeholder"
    :clearable="props.clearable"
    :disabled="props.disabled || loading"
    :loading="loading"
    check-strictly
    filterable
    @update:model-value="handleChange"
  />
</template>
