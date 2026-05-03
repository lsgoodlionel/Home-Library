<script setup lang="ts">
import { Back, Delete, Edit, StarFilled } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { deleteBook, getBook } from '@/api/books';
import { bookStatusLabel, bookStatusTagType, readStatusLabel, readStatusTagType } from '@/components/book/bookLabels';
import type { BookDetail } from '@/types/book';

const route = useRoute();
const router = useRouter();

const loading = ref(false);
const book = ref<BookDetail | null>(null);

const bookId = computed(() => Number(route.params.id));
const priceText = computed(() =>
  book.value?.priceCents === null || book.value?.priceCents === undefined
    ? '-'
    : `¥${(book.value.priceCents / 100).toFixed(2)}`,
);

async function loadBook() {
  loading.value = true;

  try {
    book.value = await getBook(bookId.value);
  } catch {
    ElMessage.error('图书详情加载失败');
  } finally {
    loading.value = false;
  }
}

async function handleDelete() {
  if (!book.value) {
    return;
  }

  try {
    await ElMessageBox.confirm(`确认删除《${book.value.title}》吗？此操作不可撤销。`, '删除图书', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
    await deleteBook(book.value.id);
    ElMessage.success('图书已删除');
    await router.push({ name: 'books' });
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败，请稍后重试');
    }
  }
}

onMounted(() => {
  void loadBook();
});
</script>

<template>
  <section v-loading="loading" class="book-detail-page">
    <el-empty v-if="!loading && !book" description="图书不存在或加载失败" />

    <template v-if="book">
      <div class="page-toolbar">
        <el-button :icon="Back" @click="router.push({ name: 'books' })">返回列表</el-button>
        <div class="toolbar-actions">
          <el-button :icon="Edit" type="primary" @click="router.push({ name: 'book-edit', params: { id: book.id } })">
            编辑
          </el-button>
          <el-button :icon="Delete" type="danger" plain @click="handleDelete">删除</el-button>
        </div>
      </div>

      <article class="detail-hero">
        <el-image v-if="book.coverUrl" :src="book.coverUrl" fit="cover" class="detail-cover" />
        <div v-else class="detail-cover detail-cover-empty">书</div>

        <div class="detail-main">
          <div class="title-row">
            <h1>{{ book.title }}</h1>
            <el-icon v-if="book.isFavorite" class="favorite-icon"><StarFilled /></el-icon>
          </div>
          <p v-if="book.subtitle" class="subtitle">{{ book.subtitle }}</p>
          <div class="meta-grid">
            <span>作者：{{ book.author || '-' }}</span>
            <span>译者：{{ book.translator || '-' }}</span>
            <span>出版社：{{ book.publisher || '-' }}</span>
            <span>出版年份：{{ book.publishYear || '-' }}</span>
            <span>ISBN：{{ book.isbn || '-' }}</span>
            <span>定价：{{ priceText }}</span>
          </div>
          <div class="tag-row">
            <el-tag :type="bookStatusTagType[book.status]">{{ bookStatusLabel[book.status] }}</el-tag>
            <el-tag :type="readStatusTagType[book.readStatus]" effect="plain">
              {{ readStatusLabel[book.readStatus] }}
            </el-tag>
            <el-rate :model-value="book.rating || 0" disabled />
          </div>
        </div>
      </article>

      <el-row :gutter="16">
        <el-col :lg="8" :xs="24">
          <el-descriptions :column="1" border title="家庭管理">
            <el-descriptions-item label="分类">
              {{ book.category ? `${book.category.code} ${book.category.name}` : '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="位置">{{ book.location?.fullPath || '-' }}</el-descriptions-item>
            <el-descriptions-item label="标签">
              <el-space wrap>
                <el-tag v-for="tag in book.tags" :key="tag.name" effect="plain">{{ tag.name }}</el-tag>
                <span v-if="book.tags.length === 0">-</span>
              </el-space>
            </el-descriptions-item>
            <el-descriptions-item label="来源">{{ book.source }}</el-descriptions-item>
          </el-descriptions>
        </el-col>

        <el-col :lg="16" :xs="24">
          <div class="text-panel">
            <h2>内容简介</h2>
            <p>{{ book.summary || '暂无内容简介。' }}</p>
          </div>
          <div class="text-panel">
            <h2>作者简介</h2>
            <p>{{ book.authorIntro || '暂无作者简介。' }}</p>
          </div>
          <div class="text-panel">
            <h2>备注</h2>
            <p>{{ book.note || '暂无备注。' }}</p>
          </div>
        </el-col>
      </el-row>
    </template>
  </section>
</template>

<style scoped>
.book-detail-page {
  display: grid;
  gap: 16px;
  min-height: 240px;
}

.page-toolbar,
.toolbar-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.detail-hero {
  display: grid;
  grid-template-columns: 148px 1fr;
  gap: 20px;
  padding: 20px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: #ffffff;
}

.detail-cover {
  width: 148px;
  height: 206px;
  border-radius: 6px;
}

.detail-cover-empty {
  display: grid;
  place-items: center;
  background: #eef3f1;
  color: var(--app-muted);
  font-size: 28px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-row h1 {
  margin: 0;
  font-size: 28px;
}

.favorite-icon {
  color: #e6a23c;
}

.subtitle {
  margin: 8px 0 18px;
  color: var(--app-muted);
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 18px;
  color: var(--app-muted);
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 20px;
}

.text-panel {
  margin-bottom: 16px;
  padding: 18px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: #ffffff;
}

.text-panel h2 {
  margin: 0 0 10px;
  font-size: 16px;
}

.text-panel p {
  margin: 0;
  color: var(--app-muted);
  line-height: 1.7;
  white-space: pre-wrap;
}

@media (max-width: 768px) {
  .detail-hero,
  .meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
