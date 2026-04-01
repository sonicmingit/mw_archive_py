import { createRouter, createWebHistory } from 'vue-router';
import LibraryView from '@/views/LibraryView.vue';
import DetailView from '@/views/DetailView.vue';
import ConfigView from '@/views/ConfigView.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: LibraryView },
    { path: '/detail/:id', name: 'detail', component: DetailView, props: true },
    { path: '/config', name: 'config', component: ConfigView }
  ],
  scrollBehavior() {
    return { top: 0 };
  }
});

export default router;
