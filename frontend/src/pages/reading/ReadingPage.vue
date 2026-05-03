<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { getBooks } from '@/api/books';
import { createBookNote, deleteNote, getBookNotes, updateNote } from '@/api/reading';
import NoteEditorDialog from '@/components/notes/NoteEditorDialog.vue';
import NotesList from '@/components/notes/NotesList.vue';
import type { BookListItem } from '@/types/book';
import type { ReadingNote, ReadingNotePayload } from '@/types/reading';

const router = useRouter();

const loading = ref(false);
const saving = ref(false);
const books = ref<BookListItem[]>([]);
const selectedBookId = ref<number | null>(null);
const selectedBookNotes = ref<ReadingNote[]>([]);
const timelineNotes = ref<ReadingNote[]>([]);
const editorVisible = ref(false);
const editingNote = ref<ReadingNote | null>(null);

const selectedBook = computed(() => books.value.find((book) => book.id === selectedBookId.value) || null);

async function loadBooks() {
  try {
    const data = await getBooks({ page: 1, pageSize: 100 });
    books.value = data.items;
    if (!selectedBookId.value && data.items.length > 0) {
      selectedBookId.value = data.items[0].id;
    }
  } catch {
    ElMessage.error('图书列表加载失败');
  }
}

async function loadSelectedBookNotes() {
  if (!selectedBookId.value) {
    selectedBookNotes.value = [];
    return;
  }

  loading.value = true;

  try {
    selectedBookNotes.value = await getBookNotes(selectedBookId.value);
  } catch {
    ElMessage.error('阅读笔记加载失败，请确认后端笔记接口可用');
    selectedBookNotes.value = [];
  } finally {
    loading.value = false;
  }
}

async function loadTimelineNotes() {
  loading.value = true;

  try {
    const results = await Promise.allSettled(books.value.map((book) => getBookNotes(book.id)));
    timelineNotes.value = results
      .flatMap((result) => (result.status === 'fulfilled' ? result.value : []))
      .sort((a, b) => (b.updatedAt || b.createdAt).localeCompare(a.updatedAt || a.createdAt));
  } catch {
    ElMessage.error('按时间读取笔记失败');
  } finally {
    loading.value = false;
  }
}

async function handleBookChange() {
  await loadSelectedBookNotes();
}

function openCreate() {
  editingNote.value = null;
  editorVisible.value = true;
}

function openEdit(note: ReadingNote) {
  editingNote.value = note;
  editorVisible.value = true;
}

async function handleSubmit(payload: ReadingNotePayload) {
  if (!selectedBookId.value && !editingNote.value) {
    ElMessage.warning('请先选择图书');
    return;
  }

  saving.value = true;

  try {
    if (editingNote.value) {
      await updateNote(editingNote.value.id, payload);
      ElMessage.success('笔记已保存');
    } else {
      await createBookNote(selectedBookId.value as number, payload);
      ElMessage.success('笔记已创建');
    }
    editorVisible.value = false;
    await loadSelectedBookNotes();
    await loadTimelineNotes();
  } catch {
    ElMessage.error('笔记保存失败，请稍后重试');
  } finally {
    saving.value = false;
  }
}

async function handleDelete(note: ReadingNote) {
  try {
    await ElMessageBox.confirm(`确认删除笔记「${note.title}」吗？`, '删除笔记', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
    await deleteNote(note.id);
    ElMessage.success('笔记已删除');
    await loadSelectedBookNotes();
    await loadTimelineNotes();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败，请稍后重试');
    }
  }
}

function viewBook(bookId: number) {
  void router.push({ name: 'book-detail', params: { id: bookId } });
}

onMounted(async () => {
  await loadBooks();
  await loadSelectedBookNotes();
  await loadTimelineNotes();
});
</script>

<template>
  <section class="reading-page">
    <div class="page-toolbar">
      <div>
        <h1>阅读笔记</h1>
        <p>按图书或时间查看、编辑阅读记录</p>
      </div>
      <el-button :icon="Plus" :disabled="!selectedBookId" type="primary" @click="openCreate">新增笔记</el-button>
    </div>

    <el-tabs>
      <el-tab-pane label="按图书查看">
        <div class="book-note-toolbar">
          <el-select v-model="selectedBookId" filterable placeholder="选择图书" @change="handleBookChange">
            <el-option
              v-for="book in books"
              :key="book.id"
              :label="`${book.title}${book.author ? ` / ${book.author}` : ''}`"
              :value="book.id"
            />
          </el-select>
          <span class="selected-book-text">{{ selectedBook?.author || '' }}</span>
        </div>

        <NotesList
          :loading="loading"
          :notes="selectedBookNotes"
          @delete="handleDelete"
          @edit="openEdit"
          @view-book="viewBook"
        />
      </el-tab-pane>

      <el-tab-pane label="按时间查看">
        <NotesList
          :loading="loading"
          :notes="timelineNotes"
          show-book
          @delete="handleDelete"
          @edit="openEdit"
          @view-book="viewBook"
        />
      </el-tab-pane>
    </el-tabs>

    <NoteEditorDialog
      v-model="editorVisible"
      :loading="saving"
      :note="editingNote"
      @submit="handleSubmit"
    />
  </section>
</template>

<style scoped>
.reading-page {
  display: grid;
  gap: 16px;
}

.page-toolbar,
.book-note-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-toolbar h1 {
  margin: 0;
  font-size: 24px;
}

.page-toolbar p,
.selected-book-text {
  margin: 6px 0 0;
  color: var(--app-muted);
}

.book-note-toolbar {
  justify-content: flex-start;
  margin-bottom: 14px;
}

.book-note-toolbar .el-select {
  width: min(460px, 100%);
}
</style>
