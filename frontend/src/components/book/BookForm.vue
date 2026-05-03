<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus';
import { computed, ref } from 'vue';

import {
  BOOK_STATUS_OPTIONS,
  READ_STATUS_OPTIONS,
  type BookFormModel,
  type CategoryOption,
  type LocationOption,
} from '@/types/book';

const props = defineProps<{
  categories: CategoryOption[];
  locations: LocationOption[];
  loading?: boolean;
}>();

const model = defineModel<BookFormModel>({ required: true });

const emit = defineEmits<{
  submit: [];
  cancel: [];
}>();

const formRef = ref<FormInstance>();

const priceYuan = computed({
  get() {
    return model.value.priceCents === null ? null : model.value.priceCents / 100;
  },
  set(value: number | null) {
    model.value.priceCents = value === null ? null : Math.round(value * 100);
  },
});

const rules: FormRules<BookFormModel> = {
  title: [{ required: true, message: '请输入书名', trigger: 'blur' }],
  publishYear: [
    {
      validator: (_rule, value, callback) => {
        const currentYear = new Date().getFullYear() + 1;
        if (value && (value < 1000 || value > currentYear)) {
          callback(new Error('请输入合理的出版年份'));
          return;
        }
        callback();
      },
      trigger: 'blur',
    },
  ],
  pages: [
    {
      validator: (_rule, value, callback) => {
        if (value !== null && value !== undefined && value <= 0) {
          callback(new Error('页数需大于 0'));
          return;
        }
        callback();
      },
      trigger: 'blur',
    },
  ],
};

async function validateAndSubmit() {
  const valid = await formRef.value?.validate();
  if (valid) {
    emit('submit');
  }
}
</script>

<template>
  <el-form ref="formRef" :model="model" :rules="rules" class="book-form" label-position="top">
    <section class="form-section">
      <h2>基础信息</h2>
      <el-row :gutter="16">
        <el-col :md="12" :xs="24">
          <el-form-item label="书名" prop="title">
            <el-input v-model="model.title" placeholder="请输入书名" />
          </el-form-item>
        </el-col>
        <el-col :md="12" :xs="24">
          <el-form-item label="副标题">
            <el-input v-model="model.subtitle" placeholder="可选" />
          </el-form-item>
        </el-col>
        <el-col :md="12" :xs="24">
          <el-form-item label="作者">
            <el-input v-model="model.author" placeholder="作者" />
          </el-form-item>
        </el-col>
        <el-col :md="12" :xs="24">
          <el-form-item label="译者">
            <el-input v-model="model.translator" placeholder="译者" />
          </el-form-item>
        </el-col>
        <el-col :xs="24">
          <el-form-item label="封面 URL">
            <el-input v-model="model.coverUrl" placeholder="https://..." />
          </el-form-item>
        </el-col>
      </el-row>
    </section>

    <section class="form-section">
      <h2>出版信息</h2>
      <el-row :gutter="16">
        <el-col :md="8" :xs="24">
          <el-form-item label="出版社">
            <el-input v-model="model.publisher" />
          </el-form-item>
        </el-col>
        <el-col :md="8" :xs="24">
          <el-form-item label="出版年份" prop="publishYear">
            <el-input-number v-model="model.publishYear" :controls="false" :min="1000" class="full-width" />
          </el-form-item>
        </el-col>
        <el-col :md="8" :xs="24">
          <el-form-item label="ISBN">
            <el-input v-model="model.isbn" placeholder="978..." />
          </el-form-item>
        </el-col>
        <el-col :md="8" :xs="24">
          <el-form-item label="语言">
            <el-input v-model="model.language" />
          </el-form-item>
        </el-col>
        <el-col :md="8" :xs="24">
          <el-form-item label="页数" prop="pages">
            <el-input-number v-model="model.pages" :controls="false" :min="1" class="full-width" />
          </el-form-item>
        </el-col>
        <el-col :md="8" :xs="24">
          <el-form-item label="定价（元）">
            <el-input-number v-model="priceYuan" :controls="false" :min="0" :precision="2" class="full-width" />
          </el-form-item>
        </el-col>
        <el-col :md="12" :xs="24">
          <el-form-item label="装帧">
            <el-input v-model="model.binding" />
          </el-form-item>
        </el-col>
        <el-col :md="12" :xs="24">
          <el-form-item label="丛书">
            <el-input v-model="model.series" />
          </el-form-item>
        </el-col>
      </el-row>
    </section>

    <section class="form-section">
      <h2>分类与位置</h2>
      <el-row :gutter="16">
        <el-col :md="8" :xs="24">
          <el-form-item label="分类">
            <el-tree-select
              v-model="model.categoryId"
              :data="props.categories"
              check-strictly
              clearable
              filterable
              node-key="id"
              placeholder="选择分类"
              :props="{ label: 'name', value: 'id', children: 'children' }"
            />
          </el-form-item>
        </el-col>
        <el-col :md="8" :xs="24">
          <el-form-item label="位置">
            <el-select v-model="model.locationId" clearable filterable placeholder="选择位置">
              <el-option
                v-for="location in props.locations"
                :key="location.id"
                :label="location.fullPath"
                :value="location.id"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :md="8" :xs="24">
          <el-form-item label="标签">
            <el-select
              v-model="model.tagNames"
              allow-create
              clearable
              default-first-option
              filterable
              multiple
              placeholder="输入后回车创建标签"
            />
          </el-form-item>
        </el-col>
      </el-row>
    </section>

    <section class="form-section">
      <h2>阅读与收藏</h2>
      <el-row :gutter="16">
        <el-col :md="6" :xs="24">
          <el-form-item label="图书状态">
            <el-select v-model="model.status">
              <el-option
                v-for="status in BOOK_STATUS_OPTIONS"
                :key="status.value"
                :label="status.label"
                :value="status.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :md="6" :xs="24">
          <el-form-item label="阅读状态">
            <el-select v-model="model.readStatus">
              <el-option
                v-for="status in READ_STATUS_OPTIONS"
                :key="status.value"
                :label="status.label"
                :value="status.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :md="6" :xs="24">
          <el-form-item label="评分">
            <el-rate v-model="model.rating" clearable />
          </el-form-item>
        </el-col>
        <el-col :md="6" :xs="24">
          <el-form-item label="重点收藏">
            <el-switch v-model="model.isFavorite" />
          </el-form-item>
        </el-col>
      </el-row>
    </section>

    <section class="form-section">
      <h2>简介与备注</h2>
      <el-form-item label="内容简介">
        <el-input v-model="model.summary" :rows="4" type="textarea" />
      </el-form-item>
      <el-form-item label="作者简介">
        <el-input v-model="model.authorIntro" :rows="3" type="textarea" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="model.note" :rows="3" type="textarea" />
      </el-form-item>
    </section>

    <div class="form-actions">
      <el-button @click="emit('cancel')">取消</el-button>
      <el-button :loading="loading" type="primary" @click="validateAndSubmit">保存</el-button>
    </div>
  </el-form>
</template>

<style scoped>
.book-form {
  display: grid;
  gap: 16px;
}

.form-section {
  padding: 18px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: #ffffff;
}

.form-section h2 {
  margin: 0 0 16px;
  font-size: 16px;
}

.full-width {
  width: 100%;
}

.form-actions {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 0;
  background: var(--app-bg);
}
</style>
