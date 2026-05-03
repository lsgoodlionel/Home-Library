<script setup lang="ts">
import { Back } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { createBook, getCategoryOptions, getLocationOptions } from '@/api/books';
import BookForm from '@/components/book/BookForm.vue';
import {
  createEmptyBookForm,
  type BookFormModel,
  type CategoryOption,
  type LocationOption,
} from '@/types/book';

const router = useRouter();

const saving = ref(false);
const loadingOptions = ref(false);
const form = ref<BookFormModel>(createEmptyBookForm());
const categories = ref<CategoryOption[]>([]);
const locations = ref<LocationOption[]>([]);

async function loadOptions() {
  loadingOptions.value = true;

  try {
    const [categoryData, locationData] = await Promise.all([
      getCategoryOptions(),
      getLocationOptions(),
    ]);
    categories.value = categoryData;
    locations.value = locationData;
  } catch {
    ElMessage.error('分类或位置选项加载失败');
  } finally {
    loadingOptions.value = false;
  }
}

async function handleSubmit() {
  saving.value = true;

  try {
    const created = await createBook(form.value);
    ElMessage.success('图书已创建');
    await router.push({ name: 'book-detail', params: { id: created.id } });
  } catch {
    ElMessage.error('创建失败，请检查表单后重试');
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void loadOptions();
});
</script>

<template>
  <section class="book-edit-page">
    <div class="page-toolbar">
      <div>
        <h1>新增图书</h1>
        <p>录入基础书目信息、分类位置和家庭管理信息</p>
      </div>
      <el-button :icon="Back" @click="router.push({ name: 'books' })">返回列表</el-button>
    </div>

    <BookForm
      v-model="form"
      v-loading="loadingOptions"
      :categories="categories"
      :loading="saving"
      :locations="locations"
      @cancel="router.push({ name: 'books' })"
      @submit="handleSubmit"
    />
  </section>
</template>

<style scoped>
.book-edit-page {
  display: grid;
  gap: 16px;
}

.page-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-toolbar h1 {
  margin: 0;
  font-size: 24px;
}

.page-toolbar p {
  margin: 6px 0 0;
  color: var(--app-muted);
}
</style>
