<script setup lang="ts">
import { Back } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import {
  bookDetailToForm,
  getBook,
  getCategoryOptions,
  getLocationOptions,
  updateBook,
} from '@/api/books';
import BookCompletionPanel from '@/components/book/BookCompletionPanel.vue';
import BookForm from '@/components/book/BookForm.vue';
import {
  createEmptyBookForm,
  type BookFormModel,
  type CategoryOption,
  type LocationOption,
} from '@/types/book';

const route = useRoute();
const router = useRouter();

const loading = ref(false);
const saving = ref(false);
const form = ref<BookFormModel>(createEmptyBookForm());
const categories = ref<CategoryOption[]>([]);
const locations = ref<LocationOption[]>([]);

const bookId = computed(() => Number(route.params.id));

async function loadData() {
  loading.value = true;

  try {
    const [book, categoryData, locationData] = await Promise.all([
      getBook(bookId.value),
      getCategoryOptions(),
      getLocationOptions(),
    ]);
    form.value = bookDetailToForm(book);
    categories.value = categoryData;
    locations.value = locationData;
  } catch {
    ElMessage.error('图书编辑数据加载失败');
  } finally {
    loading.value = false;
  }
}

async function handleSubmit() {
  saving.value = true;

  try {
    const updated = await updateBook(bookId.value, form.value);
    ElMessage.success('图书已保存');
    await router.push({ name: 'book-detail', params: { id: updated.id } });
  } catch {
    ElMessage.error('保存失败，请检查表单后重试');
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void loadData();
});
</script>

<template>
  <section v-loading="loading" class="book-edit-page">
    <div class="page-toolbar">
      <div>
        <h1>编辑图书</h1>
        <p>更新图书资料、分类位置和阅读状态</p>
      </div>
      <el-button :icon="Back" @click="router.push({ name: 'book-detail', params: { id: bookId } })">
        返回详情
      </el-button>
    </div>

    <div class="edit-layout">
      <BookCompletionPanel
        v-model="form"
        :categories="categories"
      />
      <el-card>
        <template #header>
          <div class="form-header">
            <span>图书信息</span>
            <span>可先导入简单书名，再在这里逐步补全</span>
          </div>
        </template>
        <BookForm
          v-model="form"
          :categories="categories"
          :loading="saving"
          :locations="locations"
          @cancel="router.push({ name: 'book-detail', params: { id: bookId } })"
          @submit="handleSubmit"
        />
      </el-card>
    </div>
  </section>
</template>

<style scoped>
.book-edit-page {
  display: grid;
  gap: 16px;
  min-height: 240px;
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

.edit-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.edit-layout > :first-child {
  position: sticky;
  top: 16px;
}

.form-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.form-header span:last-child {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 960px) {
  .edit-layout {
    grid-template-columns: 1fr;
  }

  .edit-layout > :first-child {
    position: static;
  }
}
</style>
