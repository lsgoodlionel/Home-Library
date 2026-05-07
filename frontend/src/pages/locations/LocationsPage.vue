<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, onMounted, reactive, ref } from 'vue';

import {
  createLocation,
  deleteLocation,
  fetchLocations,
  updateLocation,
} from '@/api/locations';
import type { CreateLocationPayload, Location, UpdateLocationPayload } from '@/types/location';

const loading = ref(false);
const locations = ref<Location[]>([]);

const dialogVisible = ref(false);
const dialogMode = ref<'create' | 'edit'>('create');
const editingId = ref<number | null>(null);
const submitting = ref(false);

const form = reactive({
  room: '',
  shelf: '',
  layer: '',
  position: '',
  description: '',
  sortOrder: 0,
});

const formRef = ref();
const formRules = {
  room: [{ required: true, message: '请输入房间名称', trigger: 'blur' }],
  shelf: [{ required: true, message: '请输入书架名称', trigger: 'blur' }],
  layer: [{ required: true, message: '请输入层数', trigger: 'blur' }],
};

const groupedByRoom = computed(() => {
  const map = new Map<string, Map<string, Location[]>>();
  for (const loc of locations.value) {
    if (!map.has(loc.room)) map.set(loc.room, new Map());
    const shelfMap = map.get(loc.room)!;
    if (!shelfMap.has(loc.shelf)) shelfMap.set(loc.shelf, []);
    shelfMap.get(loc.shelf)!.push(loc);
  }
  return map;
});

async function loadLocations() {
  loading.value = true;
  try {
    locations.value = await fetchLocations();
  } catch {
    ElMessage.error('加载位置失败');
  } finally {
    loading.value = false;
  }
}

onMounted(loadLocations);

function openCreate() {
  dialogMode.value = 'create';
  editingId.value = null;
  form.room = '';
  form.shelf = '';
  form.layer = '';
  form.position = '';
  form.description = '';
  form.sortOrder = 0;
  dialogVisible.value = true;
}

function openEdit(loc: Location) {
  dialogMode.value = 'edit';
  editingId.value = loc.id;
  form.room = loc.room;
  form.shelf = loc.shelf;
  form.layer = loc.layer;
  form.position = loc.position;
  form.description = loc.description;
  form.sortOrder = loc.sortOrder;
  dialogVisible.value = true;
}

async function handleSubmit() {
  await formRef.value.validate();
  submitting.value = true;
  try {
    if (dialogMode.value === 'create') {
      const payload: CreateLocationPayload = {
        room: form.room,
        shelf: form.shelf,
        layer: form.layer,
        position: form.position,
        description: form.description,
        sort_order: form.sortOrder,
      };
      await createLocation(payload);
      ElMessage.success('位置创建成功');
    } else {
      const payload: UpdateLocationPayload = {
        room: form.room,
        shelf: form.shelf,
        layer: form.layer,
        position: form.position,
        description: form.description,
        sort_order: form.sortOrder,
      };
      await updateLocation(editingId.value!, payload);
      ElMessage.success('位置更新成功');
    }
    dialogVisible.value = false;
    await loadLocations();
  } catch {
    ElMessage.error(dialogMode.value === 'create' ? '创建位置失败' : '更新位置失败');
  } finally {
    submitting.value = false;
  }
}

async function handleDelete(loc: Location) {
  try {
    await ElMessageBox.confirm(
      `确定删除位置「${loc.fullPath}」吗？已被图书使用的位置无法删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }

  try {
    await deleteLocation(loc.id);
    ElMessage.success('位置已删除');
    await loadLocations();
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { error?: { message?: string }; detail?: string } } };
    const msg =
      axiosErr.response?.data?.error?.message ||
      axiosErr.response?.data?.detail ||
      '删除失败，请检查该位置是否已被图书使用';
    ElMessage.error(msg);
  }
}
</script>

<template>
  <div class="locations-page">
    <div class="page-header">
      <h2 class="page-title">位置管理</h2>
      <el-button type="primary" @click="openCreate">新增位置</el-button>
    </div>

    <div v-loading="loading">
      <el-empty v-if="!loading && locations.length === 0" description="暂无位置，请点击右上角新增" />

      <template v-else>
        <div v-for="[room, shelfMap] of groupedByRoom" :key="room" class="room-section">
          <div class="room-header">
            <el-icon><component is="Location" /></el-icon>
            <span>{{ room }}</span>
            <el-tag type="info" size="small">{{ [...shelfMap.values()].flat().length }} 个位置</el-tag>
          </div>

          <div v-for="[shelf, locs] of shelfMap" :key="shelf" class="shelf-section">
            <div class="shelf-header">{{ shelf }}</div>
            <el-table :data="locs" size="small" stripe>
              <el-table-column label="完整路径" prop="fullPath" min-width="200" />
              <el-table-column label="层" prop="layer" width="120" />
              <el-table-column label="位置" prop="position" width="120" />
              <el-table-column label="说明" prop="description" show-overflow-tooltip />
              <el-table-column label="排序" prop="sortOrder" width="70" align="center" />
              <el-table-column label="操作" width="120" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
                  <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </template>
    </div>

    <!-- Create / Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新增位置' : '编辑位置'"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="80px">
        <el-form-item label="房间" prop="room">
          <el-input v-model="form.room" placeholder="如 书房" />
        </el-form-item>
        <el-form-item label="书架" prop="shelf">
          <el-input v-model="form.shelf" placeholder="如 A 架" />
        </el-form-item>
        <el-form-item label="层数" prop="layer">
          <el-input v-model="form.layer" placeholder="如 第 2 层" />
        </el-form-item>
        <el-form-item label="具体位置" prop="position">
          <el-input v-model="form.position" placeholder="可选，如 右侧" />
        </el-form-item>
        <el-form-item label="完整路径">
          <el-input
            :value="[form.room, form.shelf, form.layer, form.position].filter(Boolean).join(' / ')"
            disabled
          />
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
.locations-page {
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

.room-section {
  margin-bottom: 24px;
}

.room-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  padding: 8px 0;
  border-bottom: 2px solid var(--el-border-color);
  margin-bottom: 12px;
}

.shelf-section {
  margin-bottom: 16px;
  padding-left: 16px;
}

.shelf-header {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  margin-bottom: 8px;
}
</style>
