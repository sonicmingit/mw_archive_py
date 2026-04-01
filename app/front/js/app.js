/**
 * app.js - Vue 3 应用入口 & 路由配置
 */

(() => {
const { createApp, ref, onMounted } = Vue;
const { createRouter, createWebHashHistory } = VueRouter;

// ===== 路由配置 =====
const routes = [
    { path: '/',           name: 'home',   component: window.AppViews.HomeView },
    { path: '/detail/:id', name: 'detail', component: window.AppViews.DetailView },
    { path: '/config',     name: 'config', component: window.AppViews.ConfigView },
];

const router = createRouter({
    history: createWebHashHistory(),
    routes,
    scrollBehavior(to, from, savedPosition) {
        return savedPosition || { top: 0 };
    }
});

// ===== 根组件 =====
const App = {
    components: {
        Navbar: window.AppComponents.Navbar,
        Toast: window.AppComponents.Toast,
    },
    template: `
        <Navbar :isDark="isDark" @toggle-dark="toggleDark" @search="onSearch" />

        <main class="flex-grow flex flex-col relative">
            <router-view v-slot="{ Component }">
                <transition name="page" mode="out-in">
                    <component :is="Component" :searchKeyword="searchKeyword" />
                </transition>
            </router-view>
        </main>

        <footer class="border-t border-surfaceHigh dark:border-dBorder glass py-5 mt-auto">
            <div class="max-w-7xl mx-auto px-4 text-center text-xs text-slate-400 dark:text-slate-500">
                创客档案 &copy; 2026 &middot; MakerWorld Archive
            </div>
        </footer>

        <Toast ref="toast" />
    `,
    setup() {
        const isDark = ref(false);
        const searchKeyword = ref('');

        // 初始化暗黑模式
        const initDark = () => {
            const saved = localStorage.getItem('theme');
            if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                isDark.value = true;
                document.documentElement.classList.add('dark');
            }
        };

        const toggleDark = () => {
            isDark.value = !isDark.value;
            document.documentElement.classList.toggle('dark', isDark.value);
            localStorage.setItem('theme', isDark.value ? 'dark' : 'light');
        };

        const onSearch = (kw) => {
            searchKeyword.value = kw;
            // 搜索时如不在首页，先跳转首页
            if (router.currentRoute.value.path !== '/') {
                router.push('/');
            }
        };

        onMounted(initDark);

        return { isDark, toggleDark, searchKeyword, onSearch };
    }
};

// ===== 挂载 =====
const app = createApp(App);
app.use(router);
app.mount('#app');
})();
