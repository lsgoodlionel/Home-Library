<script setup lang="ts">
import { Refresh, Search } from '@element-plus/icons-vue';

import { BOOK_STATUS_OPTIONS, READ_STATUS_OPTIONS, type BookQuery, type CategoryOption, type LocationOption } from '@/types/book';

defineProps<{
  categories: CategoryOption[];
  locations: LocationOption[];
  loading?: boolean;
}>();

const filters = defineModel<BookQuery>({ required: true });

const emit = defineEmits<{
  search: [];
  reset: [];
}>();
</script>

<template>
  <el-form class="book-filters" label-position="top" @submit.prevent="emit('search')">
    <el-row :gutter="12">
      <el-col :lg="6" :md="8" :sm="12" :xs="24">
        <el-form-item label="关键词">
          <el-input
            v-model="filters.keyword"
            clearable
            placeholder="书名、作者、ISBN、出版社"
            @keyup.enter="emit('search')"
          />
        </el-form-item>
      </el-col>

      <el-col :lg="4" :md="8" :sm="12" :xs="24">
        <el-form-item label="分类">
          <el-tree-select
            v-model="filters.categoryId"
            :data="categories"
            check-strictly
            clearable
            node-key="id"
            placeholder="全部分类"
            :props="{ label: 'name', value: 'id', children: 'children' }"
          />
        </el-form-item>
      </el-col>

      <el-col :lg="4" :md="8" :sm="12" :xs="24">
        <el-form-item label="位置">
          <el-select v-model="filters.locationId" clearable filterable placeholder="全部位置">
            <el-option
              v-for="location in locations"
              :key="location.id"
              :label="location.fullPath"
              :value="location.id"
            />
          </el-select>
        </el-form-item>
      </el-col>

      <el-col :lg="4" :md="8" :sm="12" :xs="24">
        <el-form-item label="图书状态">
          <el-select v-model="filters.status" clearable placeholder="全部状态">
            <el-option
              v-for="status in BOOK_STATUS_OPTIONS"
              :key="status.value"
              :label="status.label"
              :value="status.value"
            />
          </el-select>
        </el-form-item>
      </el-col>

      <el-col :lg="4" :md="8" :sm="12" :xs="24">
        <el-form-item label="阅读状态">
          <el-select v-model="filters.readStatus" clearable placeholder="全部状态">
            <el-option
              v-for="status in READ_STATUS_OPTIONS"
              :key="status.value"
              :label="status.label"
              :value="status.value"
            />
          </el-select>
        </el-form-item>
      </el-col>

      <el-col :lg="2" :md="8" :sm="12" :xs="24">
        <el-form-item label="收藏">
          <el-select v-model="filters.isFavorite" clearable placeholder="全部">
            <el-option label="是" :value="true" />
            <el-option label="否" :value="false" />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <div class="book-filter-actions">
      <el-button :icon="Refresh" @click="emit('reset')">重置</el-button>
      <el-button :icon="Search" :loading="loading" native-type="submit" type="primary">搜索</el-button>
    </div>
  </el-form>
</template>

<style scoped>
.book-filters {
  padding: 16px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: #ffffff;
}

.book-filter-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
