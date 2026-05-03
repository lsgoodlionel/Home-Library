<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus';
import { onMounted, reactive, ref } from 'vue';

import { createUser, deleteUser, fetchUsers, updateUser } from '@/api/users';
import type { User, UserRole, UserStatus } from '@/types/user';

const loading = ref(false);
const users = ref<User[]>([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(20);

const filterKeyword = ref('');
const filterRole = ref<UserRole | ''>('');
const filterStatus = ref<UserStatus | ''>('');

const dialogVisible = ref(false);
const dialogMode = ref<'create' | 'edit'>('create');
const editingId = ref<number | null>(null);
const submitting = ref(false);

const formRef = ref();
const form = reactive({
  username: '',
  password: '',
  displayName: '',
  email: '',
  role: 'member' as UserRole,
  status: 'active' as UserStatus,
});

const formRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    {
      required: true,
      validator: (_: unknown, value: string, callback: (err?: Error) => void) => {
        if (dialogMode.value === 'create' && !value) {
          callback(new Error('请输入初始密码'));
        } else {
          callback();
        }
      },
      trigger: 'blur',
    },
  ],
  displayName: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
};

const roleOptions: { label: string; value: UserRole }[] = [
  { label: '管理员', value: 'admin' },
  { label: '成员', value: 'member' },
  { label: '访客', value: 'guest' },
];

const statusOptions: { label: string; value: UserStatus }[] = [
  { label: '正常', value: 'active' },
  { label: '禁用', value: 'disabled' },
];

function roleLabel(role: UserRole) {
  return roleOptions.find((o) => o.value === role)?.label ?? role;
}

async function loadUsers() {
  loading.value = true;
  try {
    const result = await fetchUsers({
      page: currentPage.value,
      page_size: pageSize.value,
      keyword: filterKeyword.value || undefined,
      role: filterRole.value || undefined,
      status: filterStatus.value || undefined,
    });
    users.value = result.items;
    total.value = result.total;
  } catch {
    ElMessage.error('加载用户列表失败');
  } finally {
    loading.value = false;
  }
}

onMounted(loadUsers);

function handleSearch() {
  currentPage.value = 1;
  loadUsers();
}

function handlePageChange(page: number) {
  currentPage.value = page;
  loadUsers();
}

function openCreate() {
  dialogMode.value = 'create';
  editingId.value = null;
  form.username = '';
  form.password = '';
  form.displayName = '';
  form.email = '';
  form.role = 'member';
  form.status = 'active';
  dialogVisible.value = true;
}

function openEdit(user: User) {
  dialogMode.value = 'edit';
  editingId.value = user.id;
  form.username = user.username;
  form.password = '';
  form.displayName = user.displayName;
  form.email = user.email;
  form.role = user.role;
  form.status = user.status;
  dialogVisible.value = true;
}

async function handleSubmit() {
  await formRef.value.validate();
  submitting.value = true;
  try {
    if (dialogMode.value === 'create') {
      await createUser({
        username: form.username,
        password: form.password,
        display_name: form.displayName,
        email: form.email,
        role: form.role,
        status: form.status,
      });
      ElMessage.success('用户创建成功');
    } else {
      await updateUser(editingId.value!, {
        display_name: form.displayName,
        email: form.email,
        role: form.role,
        status: form.status,
      });
      ElMessage.success('用户更新成功');
    }
    dialogVisible.value = false;
    await loadUsers();
  } catch {
    ElMessage.error(dialogMode.value === 'create' ? '创建用户失败' : '更新用户失败');
  } finally {
    submitting.value = false;
  }
}

async function handleToggleStatus(user: User) {
  const next: UserStatus = user.status === 'active' ? 'disabled' : 'active';
  const label = next === 'disabled' ? '禁用' : '启用';
  try {
    await ElMessageBox.confirm(
      `确定${label}用户「${user.displayName}」吗？`,
      `${label}确认`,
      { type: 'warning', confirmButtonText: label, cancelButtonText: '取消' },
    );
  } catch {
    return;
  }
  try {
    await updateUser(user.id, { status: next });
    ElMessage.success(`用户已${label}`);
    await loadUsers();
  } catch {
    ElMessage.error(`${label}失败`);
  }
}

async function handleDelete(user: User) {
  try {
    await ElMessageBox.confirm(
      `确定删除用户「${user.displayName}」吗？此操作不可恢复。建议使用禁用代替删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }
  try {
    await deleteUser(user.id);
    ElMessage.success('用户已删除');
    await loadUsers();
  } catch {
    ElMessage.error('删除失败');
  }
}
</script>

<template>
  <div class="users-page">
    <div class="page-header">
      <h2 class="page-title">用户管理</h2>
      <el-button type="primary" @click="openCreate">新增用户</el-button>
    </div>

    <el-card class="filter-card">
      <el-form inline @submit.prevent="handleSearch">
        <el-form-item label="关键词">
          <el-input
            v-model="filterKeyword"
            placeholder="用户名或显示名"
            clearable
            style="width: 200px"
            @clear="handleSearch"
          />
        </el-form-item>
        <el-form-item label="角色">
          <el-select
            v-model="filterRole"
            placeholder="全部角色"
            clearable
            style="width: 130px"
            @change="handleSearch"
          >
            <el-option v-for="o in roleOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="filterStatus"
            placeholder="全部状态"
            clearable
            style="width: 120px"
            @change="handleSearch"
          >
            <el-option
              v-for="o in statusOptions"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" native-type="submit">搜索</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-loading="loading" class="table-card">
      <el-table :data="users" border stripe row-key="id">
        <el-table-column label="ID" prop="id" width="70" />
        <el-table-column label="用户名" prop="username" min-width="130" />
        <el-table-column label="显示名称" prop="displayName" min-width="140" />
        <el-table-column label="邮箱" prop="email" min-width="180" show-overflow-tooltip />
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : row.role === 'member' ? 'primary' : 'info'">
              {{ roleLabel(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'warning'">
              {{ row.status === 'active' ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              size="small"
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="handleToggleStatus(row)"
            >
              {{ row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新增用户' : '编辑用户'"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="dialogMode === 'edit'" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item v-if="dialogMode === 'create'" label="初始密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="初始密码" />
        </el-form-item>
        <el-form-item label="显示名称" prop="displayName">
          <el-input v-model="form.displayName" placeholder="界面显示的名称" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="可选" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option v-for="o in roleOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option
              v-for="o in statusOptions"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </el-select>
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
.users-page {
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

.filter-card {
  margin-bottom: 16px;
}

.filter-card :deep(.el-card__body) {
  padding: 12px 16px 4px;
}

.table-card :deep(.el-card__body) {
  padding: 0;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding: 12px 16px;
}
</style>
