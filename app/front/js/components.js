/**
 * components.js - 全局可复用 Vue 3 组件
 */

// ===== 1. Lucide 图标封装组件 =====
const AppIcon = {
    props: {
        name: { type: String, required: true },
        size: { type: [Number, String], default: 20 },
    },
    template: `<i :data-lucide="name" style="display:inline-flex;"></i>`,
    mounted() { this._render(); },
    updated() { this._render(); },
    methods: {
        _render() {
            if (!window.lucide) return;
            this.$nextTick(() => {
                const el = this.$el;
                if (el && el.tagName) {
                    lucide.createIcons({ nameAttr: 'data-lucide', root: el.parentNode });
                    // 手动修正 svg 尺寸
                    const svg = el.tagName === 'svg' ? el : el.querySelector && el.querySelector('svg');
                    if (svg) {
                        svg.setAttribute('width', this.size);
                        svg.setAttribute('height', this.size);
                    }
                }
            });
        }
    }
};

// ===== 2. Toast 通知组件 =====
const Toast = {
    template: `
        <transition name="toast">
            <div v-if="visible"
                 class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 pointer-events-auto"
                 role="alert">
                <div class="flex items-center gap-2 px-5 py-3 rounded-xl shadow-ambient-lg text-sm font-medium"
                     :class="typeClass">
                    <span>{{ message }}</span>
                </div>
            </div>
        </transition>
    `,
    data() {
        return { visible: false, message: '', type: 'success', timer: null };
    },
    computed: {
        typeClass() {
            if (this.type === 'error') return 'bg-red-600 text-white';
            return 'bg-primary text-white';
        }
    },
    methods: {
        show(msg, type = 'success', duration = 2500) {
            clearTimeout(this.timer);
            this.message = msg;
            this.type = type;
            this.visible = true;
            this.timer = setTimeout(() => { this.visible = false; }, duration);
        }
    }
};

// ===== 3. 导航栏组件 =====
const Navbar = {
    components: { AppIcon },
    props: ['isDark'],
    emits: ['toggle-dark', 'search'],
    data() { return { keyword: '' }; },
    methods: {
        onSearch() { this.$emit('search', this.keyword); }
    },
    template: `
        <header class="sticky top-0 z-40 glass border-b border-surfaceHigh dark:border-dBorder">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <nav class="flex items-center justify-between h-16">
                    <!-- Left: Logo & Nav -->
                    <div class="flex items-center gap-6">
                        <router-link to="/" class="flex items-center gap-2.5 group cursor-pointer focus-visible:ring-2 focus-visible:ring-primary rounded-lg pr-1">
                            <div class="btn-primary-gradient p-2 rounded-lg">
                                <AppIcon name="box" :size="20" />
                            </div>
                            <span class="font-extrabold text-lg tracking-tight hidden sm:block">创客档案</span>
                        </router-link>
                        <div class="hidden md:flex items-center gap-1 bg-surfaceLow dark:bg-dCard rounded-full p-1">
                            <router-link to="/"
                                class="px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-200"
                                :class="$route.path === '/' ? 'bg-white dark:bg-dBg shadow-sm text-onSurface dark:text-white' : 'text-slate-500 dark:text-slate-400 hover:text-onSurface dark:hover:text-white'">
                                模型库
                            </router-link>
                            <router-link to="/config"
                                class="px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-200"
                                :class="$route.path === '/config' ? 'bg-white dark:bg-dBg shadow-sm text-onSurface dark:text-white' : 'text-slate-500 dark:text-slate-400 hover:text-onSurface dark:hover:text-white'">
                                设置
                            </router-link>
                        </div>
                    </div>

                    <!-- Center: Search -->
                    <div class="flex-1 max-w-md mx-4 hidden sm:block">
                        <div class="relative">
                            <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                                <AppIcon name="search" :size="16" />
                            </div>
                            <input v-model="keyword" @keyup.enter="onSearch" type="text"
                                   placeholder="搜索模型名称或标签..."
                                   class="block w-full pl-9 pr-3 py-2 border-0 rounded-full text-sm
                                          bg-surfaceLow dark:bg-dCard
                                          placeholder-slate-400 dark:placeholder-slate-500
                                          focus:bg-white dark:focus:bg-dBg
                                          transition-all duration-200">
                        </div>
                    </div>

                    <!-- Right: Actions -->
                    <div class="flex items-center gap-2">
                        <button @click="$emit('toggle-dark')"
                                class="p-2.5 rounded-full text-slate-500 dark:text-slate-400 hover:bg-surfaceHigh dark:hover:bg-dCard transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-primary"
                                :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'">
                            <AppIcon :name="isDark ? 'sun' : 'moon'" :size="18" />
                        </button>
                    </div>
                </nav>
            </div>

            <!-- Mobile nav -->
            <div class="md:hidden border-t border-surfaceHigh dark:border-dBorder px-4 py-1.5 flex gap-1">
                <router-link to="/"
                    class="flex-1 text-center text-sm font-medium py-1.5 rounded-full transition-all"
                    :class="$route.path === '/' ? 'bg-white dark:bg-dBg shadow-sm' : 'text-slate-500'">
                    模型库
                </router-link>
                <router-link to="/config"
                    class="flex-1 text-center text-sm font-medium py-1.5 rounded-full transition-all"
                    :class="$route.path === '/config' ? 'bg-white dark:bg-dBg shadow-sm' : 'text-slate-500'">
                    设置
                </router-link>
            </div>
        </header>
    `
};

// ===== 4. 模型卡片组件 =====
const ModelCard = {
    components: { AppIcon },
    props: { model: { type: Object, required: true } },
    template: `
        <router-link :to="'/detail/' + model.id"
            class="group flex flex-col bg-white dark:bg-dCard rounded-xl overflow-hidden cursor-pointer
                   shadow-ambient hover:shadow-ambient-lg
                   hover:ring-2 hover:ring-primary/40
                   transition-all duration-300
                   focus-visible:ring-2 focus-visible:ring-primary">

            <!-- Cover -->
            <div class="relative aspect-[4/3] w-full bg-surfaceLow dark:bg-slate-800 overflow-hidden img-matte">
                <div v-if="model.cover_image"
                     class="w-full h-full bg-cover bg-center rounded transition-transform duration-500 group-hover:scale-105"
                     :style="{ backgroundImage: 'url(' + model.cover_image + ')' }">
                </div>
                <div v-else class="w-full h-full flex items-center justify-center text-slate-300 dark:text-slate-600 rounded bg-surfaceMid dark:bg-slate-800/60">
                    <AppIcon name="image" :size="40" />
                </div>

                <!-- Download badge -->
                <div class="absolute top-3 left-3 bg-black/50 backdrop-blur-md text-white text-[11px] font-medium px-2 py-0.5 rounded-md flex items-center gap-1">
                    <AppIcon name="download" :size="12" />
                    {{ model.downloads }}
                </div>
            </div>

            <!-- Info -->
            <div class="p-4 flex flex-col flex-grow">
                <h3 class="font-semibold text-sm leading-snug line-clamp-2 group-hover:text-primary transition-colors mb-3">
                    {{ model.title }}
                </h3>

                <div class="mt-auto flex items-center gap-2">
                    <div class="w-6 h-6 rounded-full bg-primary/15 text-primary flex items-center justify-center text-[10px] font-bold shrink-0">
                        {{ model.author ? model.author.charAt(0) : '?' }}
                    </div>
                    <span class="text-xs text-slate-500 dark:text-slate-400 truncate">{{ model.author }}</span>
                </div>
            </div>
        </router-link>
    `
};

// ===== 5. 骨架屏卡片 =====
const SkeletonCard = {
    template: `
        <div class="flex flex-col rounded-xl overflow-hidden">
            <div class="aspect-[4/3] skeleton"></div>
            <div class="p-4 space-y-3">
                <div class="h-4 skeleton w-3/4"></div>
                <div class="h-3 skeleton w-1/2"></div>
            </div>
        </div>
    `
};

// ===== Export =====
window.AppComponents = { AppIcon, Toast, Navbar, ModelCard, SkeletonCard };
