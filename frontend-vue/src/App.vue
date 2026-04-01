<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Grid2x2, MoonStar, Search, Settings2, SunMedium } from 'lucide-vue-next';

const router = useRouter();
const route = useRoute();

const theme = ref(localStorage.getItem('mw_vue_theme') || 'light');
const searchValue = ref(typeof route.query.q === 'string' ? route.query.q : '');
const isHome = computed(() => route.name === 'home');

function applyTheme(nextTheme) {
  theme.value = nextTheme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme.value;
  localStorage.setItem('mw_vue_theme', theme.value);
}

function toggleTheme() {
  applyTheme(theme.value === 'dark' ? 'light' : 'dark');
}

function goHome() {
  router.push({ name: 'home', query: searchValue.value ? { q: searchValue.value } : {} });
}

function goConfig() {
  router.push({ name: 'config' });
}

watch(
  () => route.query.q,
  (next) => {
    searchValue.value = typeof next === 'string' ? next : '';
  }
);

watch(searchValue, (next) => {
  if (!isHome.value) return;
  const current = typeof route.query.q === 'string' ? route.query.q : '';
  if (current === next) return;
  router.replace({ name: 'home', query: next ? { q: next } : {} });
});

onMounted(() => applyTheme(theme.value));
</script>

<template>
  <div class="shell">
    <header class="topbar panel panel-blur">
      <button class="brand" type="button" @click="goHome">
        <span class="brand-mark">
          <img src="/fav.png" alt="logo" />
        </span>
        <span>
          <strong>MakerWorld Archive</strong>
          <small>本地模型库</small>
        </span>
      </button>

      <div class="search-box">
        <Search :size="18" />
        <input v-model="searchValue" type="search" placeholder="搜索模型名称或标签..." :disabled="!isHome" />
      </div>

      <div class="topbar-actions">
        <button class="btn btn-secondary" type="button" @click="goHome">
          <Grid2x2 :size="16" />
          首页
        </button>
        <button class="btn btn-primary" type="button" @click="goConfig">
          <Settings2 :size="16" />
          控制台
        </button>
        <button class="btn btn-secondary btn-icon" type="button" @click="toggleTheme">
          <MoonStar v-if="theme === 'light'" :size="17" />
          <SunMedium v-else :size="17" />
        </button>
      </div>
    </header>

    <main class="page-wrap">
      <RouterView />
    </main>
  </div>
</template>
