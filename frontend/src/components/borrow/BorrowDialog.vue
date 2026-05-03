<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus';
import { ref, watch } from 'vue';

import type { BookListItem } from '@/types/book';
import { createEmptyBorrowPayload, type BorrowCreatePayload } from '@/types/borrow';

const props = defineProps<{
  books: BookListItem[];
  defaultBookId?: number;
  loading?: boolean;
}>();

const visible = defineModel<boolean>({ required: true });

const emit = defineEmits<{
  submit: [payload: BorrowCreatePayload];
}>();

const formRef = ref<FormInstance>();
const form = ref<BorrowCreatePayload>(createEmptyBorrowPayload(props.defaultBookId || 0));

const rules: FormRules<BorrowCreatePayload> = {
  bookId: [{ required: true, message: '请选择图书', trigger: 'change' }],
  borrowerName: [{ required: true, message: '请输入借阅人', trigger: 'blur' }],
  borrowedAt: [{ required: true, message: '请选择借出日期', trigger: 'change' }],
};

watch(
  () => visible.value,
  (next) => {
    if (next) {
      form.value = createEmptyBorrowPayload(props.defaultBookId || 0);
    }
  },
);

async function handleSubmit() {
  const valid = await formRef.value?.validate();
  if (valid) {
    emit('submit', { ...form.value });
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="借出图书" width="520px">
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="图书" prop="bookId">
        <el-select v-model="form.bookId" filterable placeholder="选择要借出的图书">
          <el-option
            v-for="book in books"
            :key="book.id"
            :label="`${book.title}${book.author ? ` / ${book.author}` : ''}`"
            :value="book.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="借阅人" prop="borrowerName">
        <el-input v-model="form.borrowerName" />
      </el-form-item>

      <el-form-item label="联系方式">
        <el-input v-model="form.borrowerContact" />
      </el-form-item>

      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="借出日期" prop="borrowedAt">
            <el-date-picker v-model="form.borrowedAt" type="date" value-format="YYYY-MM-DD" class="full-width" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="应还日期">
            <el-date-picker v-model="form.dueAt" type="date" value-format="YYYY-MM-DD" class="full-width" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="备注">
        <el-input v-model="form.note" :rows="3" type="textarea" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button :loading="loading" type="primary" @click="handleSubmit">确认借出</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.full-width {
  width: 100%;
}
</style>
