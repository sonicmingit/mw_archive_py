<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { CheckSquare, FolderHeart, Minimize2, RefreshCw, SearchX } from 'lucide-vue-next';
import FolderModal from '@/components/FolderModal.vue';
import ModelCard from '@/components/ModelCard.vue';
import SidebarFilters from '@/components/SidebarFilters.vue';
import { getLibrary, getSourceOptions, saveFolder, toggleFavorite } from '@/api/models';

const router = useRouter();
const route = useRoute();

const loading = ref(false);
const compactMode = ref(false);
const batchMode = ref(false);
const sortBy = ref('archivedDate');
const selectedIds = ref([]);
const folderModalOpen = ref(false);

const store = reactive({
  models: [],
  folders: []
});

const filters = reactive({
  source: 'all',
  folder: '',
  category: '',
  favoritesOnly: false,
  printedOnly: false
});

const categories = computed(() => [...new Set(store.models.map((item) => item.category).filter(Boolean))]);

const sidebarSources = computed(() =>
  getSourceOptions().map((option) => ({
    ...option,
    count: option.id === 'all' ? store.models.length : store.models.filter((item) => item.source === option.id).length
  }))
);

const filteredModels = computed(() => {
  let list = [...store.models];
  const search = typeof route.query.q === 'string' ? route.query.q.trim().toLowerCase() : '';

  if (search) {
    list = list.filter((item) => item.title.toLowerCase().includes(search) || item.tags.some((tag) => tag.toLowerCase().includes(search)));
  }
  if (filters.source !== 'all') list = list.filter((item) => item.source === filters.source);
  if (filters.category) list = list.filter((item) => item.category === filters.category);
  if (filters.folder) {
    const folder = store.folders.find((item) => item.id === filters.folder);
    const ids = new Set(folder ? folder.modelIds : []);
    list = list.filter((item) => ids.has(item.id));
  }
  if (filters.favoritesOnly) list = list.filter((item) => item.isFavorited);
  if (filters.printedOnly) list = list.filter((item) => item.isPrinted);

  const dateValue = (value) => new Date(value || '').getTime() || 0;
  list.sort((a, b) => {
    if (sortBy.value === 'downloads' || sortBy.value === 'favorites') return (b[sortBy.value] || 0) - (a[sortBy.value] || 0);
    return dateValue(b[sortBy.value]) - dateValue(a[sortBy.value]);
  });
  return list;
});

async function loadLibraryData() {
  loading.value = true;
  try {
    const data = await getLibrary();
    store.models = data.models;
    store.folders = data.folders;
  } finally {
    loading.value = false;
  }
}

function openDetail(id) {
  router.push({ name: 'detail', params: { id } });
}

function toggleBatchMode() {
  batchMode.value = !batchMode.value;
  if (!batchMode.value) selectedIds.value = [];
}

function toggleSelection(id) {
  const next = new Set(selectedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selectedIds.value = [...next];
}

function clearSelection() {
  selectedIds.value = [];
}

async function onToggleFavorite(id) {
  await toggleFavorite(id);
  await loadLibraryData();
}

async function handleSaveFolder(folderDraft) {
  await saveFolder(folderDraft, selectedIds.value);
  folderModalOpen.value = false;
  selectedIds.value = [];
  await loadLibraryData();
}

onMounted(loadLibraryData);
</script>

<template>
  <div class="library-layout">
    <SidebarFilters
      :sources="sidebarSources"
      :folders="store.folders"
      :categories="categories"
      :selected-source="filters.source"
      :selected-folder="filters.folder"
      :selected-category="filters.category"
      :favorites-only="filters.favoritesOnly"
      :printed-only="filters.printedOnly"
      @select-source="filters.source = $event"
      @select-folder="filters.folder = $event"
      @select-category="filters.category = $event"
      @toggle-favorites="filters.favoritesOnly = !filters.favoritesOnly"
      @toggle-printed="filters.printedOnly = !filters.printedOnly"
    />

    <section class="library-main">
      <div class="panel hero-panel">
        <div>
          <h1>本地模型库</h1>
          <p>完全独立的 Vue 3 前端，直接请求已运行的后端接口。</p>
        </div>
        <div class="toolbar">
          <button class="btn btn-secondary" type="button" :class="{ active: batchMode }" @click="toggleBatchMode">
            <CheckSquare :size="16" />
            多选
          </button>
          <button class="btn btn-secondary" type="button" :class="{ active: compactMode }" @click="compactMode = !compactMode">
            <Minimize2 :size="16" />
            简洁模式
          </button>
          <select v-model="sortBy" class="field select-inline">
            <option value="archivedDate">采集时间倒序</option>
            <option value="publishDate">发布时间倒序</option>
            <option value="downloads">下载量</option>
            <option value="favorites">收藏数</option>
          </select>
          <button class="btn btn-secondary" type="button" @click="loadLibraryData">
            <RefreshCw :size="16" />
            刷新
          </button>
        </div>

        <div v-if="batchMode" class="selection-panel">
          <span>已选 {{ selectedIds.length }} 项</span>
          <div class="toolbar">
            <button class="btn btn-primary" type="button" :disabled="!selectedIds.length" @click="folderModalOpen = true">
              <FolderHeart :size="16" />
              批量收藏
            </button>
            <button class="btn btn-secondary" type="button" :disabled="!selectedIds.length" @click="clearSelection">
              清空选择
            </button>
          </div>
        </div>
      </div>

      <div v-if="loading" class="panel empty-state">
        <div class="spinner" />
      </div>
      <div v-else-if="filteredModels.length" class="card-grid" :class="{ compact: compactMode }">
        <ModelCard
          v-for="model in filteredModels"
          :key="model.id"
          :model="model"
          :compact="compactMode"
          :batch-mode="batchMode"
          :selected="selectedIds.includes(model.id)"
          @open="openDetail"
          @toggle-select="toggleSelection"
          @toggle-favorite="onToggleFavorite"
        />
      </div>
      <div v-else class="panel empty-state">
        <SearchX :size="32" />
        <h3>没有匹配的模型</h3>
        <p>调整搜索词或筛选条件后再试。</p>
      </div>
    </section>

    <FolderModal
      :open="folderModalOpen"
      :folders="store.folders"
      :selected-count="selectedIds.length"
      @close="folderModalOpen = false"
      @save="handleSaveFolder"
    />
  </div>
</template>
