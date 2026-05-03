<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus';
import { ref, watch } from 'vue';

import type { BorrowRecord, BorrowReturnPayload } from '@/types/borrow';

const props = defineProps<{
  record: BorrowRecord | null;
  loading?: boolean;
}>();

const visible = defineModel<boolean>({ required: true });

const emit = defineEmits<{
  submit: [id: number, payload: BorrowReturnPayload];
}>();

const formRef = ref<FormInstance>();
const form = ref<BorrowReturnPayload>({
  returnedAt: new Date().toISOString().slice(0, 10),
  note: '',
});

const rules: FormRules<BorrowReturnPayload> = {
  returnedAt: [{ required: true, message: '请选择归还日期', trigger: 'change' }],
};

watch(
  () => visible.value,
  (next) => {
    if (next) {
      form.value = {
        returnedAt: new Date().toISOString().slice(0, 10),
        note: '',
      };
    }
  },
);

async function handleSubmit() {
  if (!props.record) {
    return;
  }
  const valid = await formRef.value?.validate();
  if (valid) {
    emit('submit', props.record.id, { ...form.value });
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="归还图书" width="460px">
    <p class="return-title">{{ record?.book?.title || `图书 #${record?.bookId || ''}` }}</p>

    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="归还日期" prop="returnedAt">
        <el-date-picker v-model="form.returnedAt" type="date" value-format="YYYY-MM-DD" class="full-width" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.note" :rows="3" type="textarea" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button :loading="loading" type="primary" @click="handleSubmit">确认归还</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.return-title {
  margin: 0 0 16px;
  color: var(--app-muted);
}

.full-width {
  width: 100%;
}
</style>
