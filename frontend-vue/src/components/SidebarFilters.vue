<script setup>
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { BadgeCheck, Filter, FolderHeart, Globe, Heart, Settings, Tags } from 'lucide-vue-next';

const props = defineProps({
  sources: { type: Array, required: true },
  folders: { type: Array, required: true },
  categories: { type: Array, required: true },
  selectedSource: { type: String, default: 'all' },
  selectedFolder: { type: String, default: '' },
  selectedCategory: { type: String, default: '' },
  favoritesOnly: { type: Boolean, default: false },
  printedOnly: { type: Boolean, default: false }
});

const emit = defineEmits(['select-source', 'select-folder', 'select-category', 'toggle-favorites', 'toggle-printed']);

const folderItems = computed(() => [{ id: '', name: '全部', modelIds: [] }, ...props.folders]);
const router = useRouter();
</script>

<template>
  <aside class="sidebar panel">
    <section class="side-section">
      <div class="side-title"><Globe :size="16" />来源分组</div>
      <button
        v-for="source in sources"
        :key="source.id"
        class="side-item"
        :class="{ active: selectedSource === source.id }"
        type="button"
        @click="emit('select-source', source.id)"
      >
        <span>{{ source.label }}</span>
        <span class="side-count">{{ source.count }}</span>
      </button>
    </section>

    <section class="side-section">
      <div class="side-title"><Filter :size="16" />筛选选项</div>
      <button class="side-item" :class="{ active: favoritesOnly }" type="button" @click="emit('toggle-favorites')">
        <span><Heart :size="15" />只看收藏</span>
      </button>
      <button class="side-item" :class="{ active: printedOnly }" type="button" @click="emit('toggle-printed')">
        <span><BadgeCheck :size="15" />只看已打印</span>
      </button>
    </section>

    <section class="side-section">
      <div class="side-title"><FolderHeart :size="16" />收藏夹</div>
      <button
        v-for="folder in folderItems"
        :key="folder.id || 'all'"
        class="side-item"
        :class="{ active: selectedFolder === folder.id }"
        type="button"
        @click="emit('select-folder', folder.id)"
      >
        <span>{{ folder.name }}</span>
        <span v-if="folder.id" class="side-count">{{ folder.modelIds.length }}</span>
      </button>
    </section>

    <section class="side-section">
      <div class="side-title"><Tags :size="16" />分类</div>
      <div class="chip-list">
        <button class="chip" :class="{ active: !selectedCategory }" type="button" @click="emit('select-category', '')">全部</button>
        <button
          v-for="category in categories"
          :key="category"
          class="chip"
          :class="{ active: selectedCategory === category }"
          type="button"
          @click="emit('select-category', category)"
        >
          {{ category }}
        </button>
      </div>
    </section>

    <section class="side-section side-footer">
      <button class="side-item" type="button" @click="router.push({ name: 'config' })">
        <span><Settings :size="15" />控制台</span>
      </button>
    </section>
  </aside>
</template>
