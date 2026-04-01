(() => {
const { createApp, ref, onMounted } = Vue;
const { createRouter, createWebHashHistory } = VueRouter;

const routes = [
    { path: '/', name: 'home', component: window.AppViews.HomeView, props: true },
    { path: '/detail/:id', name: 'detail', component: window.AppViews.DetailView },
    { path: '/config', name: 'config', component: window.AppViews.ConfigView }
];

const router = createRouter({
    history: createWebHashHistory(),
    routes,
    scrollBehavior() {
        return { top: 0 };
    }
});

const App = {
    components: {
        AppIcon: window.AppComponents.AppIcon,
        AppToast: window.AppComponents.AppToast
    },
    template: `
        <div class="min-h-screen">
            <header class="sticky top-0 z-50 border-b border-borderSoft glass-dark">
                <div class="mx-auto flex max-w-[1680px] items-center gap-4 px-5 py-4">
                    <button type="button" class="inline-flex items-center gap-3" @click="goHome">
                        <span class="inline-flex h-11 w-11 items-center justify-center overflow-hidden rounded-2xl border border-borderSoft bg-white shadow-glow">
                            <img src="./fav.png" alt="logo" class="h-full w-full object-cover">
                        </span>
                        <div class="text-left">
                            <div class="text-[15px] font-extrabold tracking-wide text-cyan">本地模型库</div>
                            <div class="text-xs text-textMuted">Vue SPA · Frontend / Backend</div>
                        </div>
                    </button>

                    <div class="relative mx-auto w-full max-w-[560px]">
                        <span class="pointer-events-none absolute inset-y-0 left-4 flex items-center text-textMuted">
                            <AppIcon name="search" :size="18" />
                        </span>
                        <input v-model="searchKeyword" type="text" class="input-dark !rounded-full !bg-panelHard !pl-11" placeholder="搜索模型名称或标签...">
                    </div>

                    <div class="flex items-center gap-2">
                        <button type="button" class="secondary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-2.5" @click="goConfig">
                            <AppIcon name="settings-2" :size="16" />配置
                        </button>
                        <button type="button" class="secondary-btn inline-flex h-11 w-11 items-center justify-center rounded-2xl" @click="toggleTheme">
                            <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
                        </button>
                    </div>
                </div>
            </header>

            <main>
                <router-view :search-keyword="searchKeyword"></router-view>
            </main>

            <AppToast ref="toast" />
        </div>
    `,
    setup() {
        const searchKeyword = ref('');
        const theme = ref('dark');

        function applyTheme(nextTheme) {
            theme.value = nextTheme === 'light' ? 'light' : 'dark';
            document.documentElement.classList.toggle('dark', theme.value === 'dark');
            document.documentElement.classList.toggle('light-theme', theme.value === 'light');
            localStorage.setItem('mw_figma_theme', theme.value);
        }

        function toggleTheme() {
            applyTheme(theme.value === 'dark' ? 'light' : 'dark');
        }

        function goHome() { router.push('/'); }
        function goConfig() { router.push('/config'); }

        onMounted(() => {
            applyTheme(localStorage.getItem('mw_figma_theme') || 'dark');
        });

        return { searchKeyword, goHome, goConfig, theme, toggleTheme };
    }
};

const app = createApp(App);
app.use(router);
app.mount('#app');
})();
