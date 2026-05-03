<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus';
import { ref, watch } from 'vue';

import {
  createEmptyReadingNotePayload,
  type ReadingNote,
  type ReadingNotePayload,
} from '@/types/reading';

const props = defineProps<{
  note?: ReadingNote | null;
  loading?: boolean;
}>();

const visible = defineModel<boolean>({ required: true });

const emit = defineEmits<{
  submit: [payload: ReadingNotePayload];
}>();

const formRef = ref<FormInstance>();
const form = ref<ReadingNotePayload>(createEmptyReadingNotePayload());

const rules: FormRules<ReadingNotePayload> = {
  title: [{ required: true, message: '请输入笔记标题', trigger: 'blur' }],
};

watch(
  () => visible.value,
  (next) => {
    if (!next) {
      return;
    }
    form.value = props.note
      ? {
          title: props.note.title,
          content: props.note.content,
          progress: props.note.progress,
          rating: props.note.rating,
          startedAt: props.note.startedAt,
          finishedAt: props.note.finishedAt,
        }
      : createEmptyReadingNotePayload();
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
  <el-dialog v-model="visible" :title="note ? '编辑阅读笔记' : '新增阅读笔记'" width="680px">
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="标题" prop="title">
        <el-input v-model="form.title" />
      </el-form-item>

      <el-row :gutter="12">
        <el-col :md="8" :xs="24">
          <el-form-item label="阅读进度">
            <el-input-number v-model="form.progress" :max="100" :min="0" class="full-width" />
          </el-form-item>
        </el-col>
        <el-col :md="8" :xs="24">
          <el-form-item label="评分">
            <el-rate v-model="form.rating" clearable />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :md="12" :xs="24">
          <el-form-item label="开始日期">
            <el-date-picker v-model="form.startedAt" type="date" value-format="YYYY-MM-DD" class="full-width" />
          </el-form-item>
        </el-col>
        <el-col :md="12" :xs="24">
          <el-form-item label="完成日期">
            <el-date-picker v-model="form.finishedAt" type="date" value-format="YYYY-MM-DD" class="full-width" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="内容">
        <el-input
          v-model="form.content"
          :autosize="{ minRows: 8, maxRows: 16 }"
          placeholder="支持 Markdown 文本"
          type="textarea"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button :loading="loading" type="primary" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.full-width {
  width: 100%;
}
</style>
