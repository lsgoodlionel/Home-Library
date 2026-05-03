<script setup lang="ts">
import { Lock } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { onMounted, reactive, ref } from 'vue';

import {
  createCategory,
  deleteCategory,
  fetchCategories,
  updateCategory,
} from '@/api/categories';
import type { Category, CreateCategoryPayload, UpdateCategoryPayload } from '@/types/category';

const treeProps = { label: 'name', children: 'children' };

const loading = ref(false);
const treeData = ref<Category[]>([]);
const selectedCategory = ref<Category | null>(null);

const dialogVisible = ref(false);
const dialogMode = ref<'create' | 'edit'>('create');
const dialogParentId = ref<number | null>(null);
const dialogParentName = ref('根分类');
const submitting = ref(false);

const form = reactive({
  code: '',
  name: '',
  description: '',
  sortOrder: 0,
});

const formRef = ref();
const formRules = {
  code: [{ required: true, message: '请输入分类号', trigger: 'blur' }],
  name: [{ required: true, message: '请输入分类名称', trigger: 'blur' }],
};

async function loadCategories() {
  loading.value = true;
  try {
    treeData.value = await fetchCategories();
  } catch {
    ElMessage.error('加载分类失败');
  } finally {
    loading.value = false;
  }
}

onMounted(loadCategories);

function handleNodeClick(data: Category) {
  selectedCategory.value = data;
}

function openCreateRoot() {
  dialogMode.value = 'create';
  dialogParentId.value = null;
  dialogParentName.value = '根分类';
  form.code = '';
  form.name = '';
  form.description = '';
  form.sortOrder = 0;
  dialogVisible.value = true;
}

function openCreateChild(parent: Category) {
  dialogMode.value = 'create';
  dialogParentId.value = parent.id;
  dialogParentName.value = `${parent.code} ${parent.name}`;
  form.code = '';
  form.name = '';
  form.description = '';
  form.sortOrder = 0;
  dialogVisible.value = true;
}

function openEdit(cat: Category) {
  dialogMode.value = 'edit';
  dialogParentId.value = cat.parentId;
  dialogParentName.value = cat.parentId ? '（父分类）' : '根分类';
  form.code = cat.code;
  form.name = cat.name;
  form.description = cat.description;
  form.sortOrder = cat.sortOrder;
  dialogVisible.value = true;
}

async function handleSubmit() {
  await formRef.value.validate();
  submitting.value = true;
  try {
    if (dialogMode.value === 'create') {
      const payload: CreateCategoryPayload = {
        code: form.code,
        name: form.name,
        parent_id: dialogParentId.value,
        description: form.description,
        sort_order: form.sortOrder,
      };
      await createCategory(payload);
      ElMessage.success('分类创建成功');
    } else {
      const payload: UpdateCategoryPayload = {
        code: form.code,
        name: form.name,
        description: form.description,
        sort_order: form.sortOrder,
      };
      await updateCategory(selectedCategory.value!.id, payload);
      ElMessage.success('分类更新成功');
    }
    dialogVisible.value = false;
    selectedCategory.value = null;
    await loadCategories();
  } catch {
    ElMessage.error(dialogMode.value === 'create' ? '创建分类失败' : '更新分类失败');
  } finally {
    submitting.value = false;
  }
}

async function handleDelete(cat: Category) {
  try {
    await ElMessageBox.confirm(
      `确定删除分类「${cat.code} ${cat.name}」吗？系统分类和已被图书使用的分类无法删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }

  try {
    await deleteCategory(cat.id);
    ElMessage.success('分类已删除');
    selectedCategory.value = null;
    await loadCategories();
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { error?: { message?: string }; detail?: string } } };
    const msg =
      axiosErr.response?.data?.error?.message ||
      axiosErr.response?.data?.detail ||
      '删除失败，请检查该分类是否已被图书使用';
    ElMessage.error(msg);
  }
}
</script>

<template>
  <div class="categories-page">
    <div class="page-header">
      <h2 class="page-title">分类管理</h2>
      <el-button type="primary" @click="openCreateRoot">新增根分类</el-button>
    </div>

    <el-row :gutter="16" class="page-body">
      <!-- Tree panel -->
      <el-col :span="8">
        <el-card class="tree-card" v-loading="loading">
          <template #header>
            <span>分类树</span>
          </template>

          <el-empty v-if="!loading && treeData.length === 0" description="暂无分类" />

          <el-tree
            v-else
            :data="treeData"
            :props="treeProps"
            node-key="id"
            :default-expand-all="true"
            highlight-current
            @node-click="handleNodeClick"
          >
            <template #default="{ data }">
              <span class="tree-node">
                <el-icon v-if="(data as Category).isSystem" class="lock-icon">
                  <Lock />
                </el-icon>
                <span class="node-code">{{ (data as Category).code }}</span>
                <span class="node-name">{{ (data as Category).name }}</span>
              </span>
            </template>
          </el-tree>
        </el-card>
      </el-col>

      <!-- Detail panel -->
      <el-col :span="16">
        <el-card class="detail-card">
          <template #header>
            <span>分类详情</span>
          </template>

          <el-empty v-if="!selectedCategory" description="请在左侧选择一个分类" />

          <template v-else>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="分类号">
                {{ selectedCategory.code }}
              </el-descriptions-item>
              <el-descriptions-item label="分类名称">
                {{ selectedCategory.name }}
              </el-descriptions-item>
              <el-descriptions-item label="类型">
                <el-tag v-if="selectedCategory.isSystem" type="info">
                  <el-icon><Lock /></el-icon>
                  系统分类
                </el-tag>
                <el-tag v-else type="success">自定义</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="排序">
                {{ selectedCategory.sortOrder }}
              </el-descriptions-item>
              <el-descriptions-item label="说明" :span="2">
                {{ selectedCategory.description || '—' }}
              </el-descriptions-item>
            </el-descriptions>

            <div class="detail-actions">
              <el-button @click="openCreateChild(selectedCategory)">新增子分类</el-button>
              <el-button type="primary" @click="openEdit(selectedCategory)">编辑</el-button>
              <el-button
                type="danger"
                :disabled="selectedCategory.isSystem"
                @click="handleDelete(selectedCategory)"
              >
                删除
              </el-button>
            </div>

            <el-alert
              v-if="selectedCategory.isSystem"
              type="info"
              :closable="false"
              show-icon
              title="系统内置分类，不可删除，可编辑说明和排序"
              class="system-alert"
            />
          </template>
        </el-card>
      </el-col>
    </el-row>

    <!-- Create / Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新增分类' : '编辑分类'"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="80px">
        <el-form-item label="父分类">
          <el-input :value="dialogParentName" disabled />
        </el-form-item>
        <el-form-item label="分类号" prop="code">
          <el-input v-model="form.code" placeholder="如 I247" />
        </el-form-item>
        <el-form-item label="分类名称" prop="name">
          <el-input v-model="form.name" placeholder="如 中国当代小说" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sortOrder" :min="0" :max="9999" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ dialogMode === 'create' ? '创建' : '保存' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.categories-page {
  padding: 0;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.page-body {
  align-items: flex-start;
}

.tree-card,
.detail-card {
  min-height: 480px;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 4px;
}

.lock-icon {
  color: var(--el-color-info);
  font-size: 12px;
}

.node-code {
  color: var(--el-color-info);
  font-size: 12px;
  margin-right: 2px;
}

.node-name {
  font-size: 14px;
}

.detail-actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}

.system-alert {
  margin-top: 12px;
}
</style>
