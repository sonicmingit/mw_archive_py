/**
 * views.js - Vue 3 页面视图组件
 */

(() => {
const { ref, reactive, onMounted, watch, computed } = Vue;

// ===== 1. 首页 - 模型库 =====
const HomeView = {
    components: {
        ModelCard: window.AppComponents.ModelCard,
        SkeletonCard: window.AppComponents.SkeletonCard,
        AppIcon: window.AppComponents.AppIcon
    },
    props: ['searchKeyword'],
    template: `
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full flex-grow">
            <!-- Header -->
            <div class="flex items-center justify-between mb-8">
                <div>
                    <h1 class="text-3xl font-extrabold tracking-tight">模型库</h1>
                    <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">共 {{ filteredModels.length }} 个模型</p>
                </div>
                <div class="flex gap-2">
                    <button @click="sortBy = sortBy === 'downloads' ? 'likes' : 'downloads'"
                            class="flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg
                                   bg-surfaceLow dark:bg-dCard hover:bg-surfaceHigh dark:hover:bg-dBorder
                                   transition-colors cursor-pointer">
                        <AppIcon name="arrow-up-down" :size="15" />
                        <span>{{ sortBy === 'downloads' ? '按下载量' : '按收藏数' }}</span>
                    </button>
                    <button class="flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg
                                   btn-primary-gradient cursor-pointer">
                        <AppIcon name="folder-sync" :size="15" />
                        <span>同步</span>
                    </button>
                </div>
            </div>

            <!-- Tag Filters -->
            <div class="flex flex-wrap gap-2 mb-6">
                <button v-for="tag in allTags" :key="tag"
                        @click="toggleTag(tag)"
                        class="tag-chip cursor-pointer transition-all duration-200"
                        :class="selectedTags.includes(tag)
                            ? 'bg-primary text-white'
                            : 'bg-surfaceMid dark:bg-dCard text-slate-600 dark:text-slate-400 hover:bg-surfaceHigh dark:hover:bg-dBorder'">
                    {{ tag }}
                </button>
            </div>

            <!-- Loading Skeleton -->
            <div v-if="loading" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                <SkeletonCard v-for="n in 8" :key="n" />
            </div>

            <!-- Grid -->
            <div v-else-if="filteredModels.length > 0"
                 class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                <ModelCard v-for="model in filteredModels" :key="model.id" :model="model" />
            </div>

            <!-- Empty -->
            <div v-else class="flex flex-col items-center justify-center py-20 text-slate-400">
                <AppIcon name="inbox" :size="48" />
                <p class="text-base font-medium mt-4">未找到匹配的模型</p>
                <p class="text-sm mt-1">尝试修改搜索关键词或清除筛选条件</p>
                <button @click="clearFilters" class="mt-4 text-sm text-primary hover:underline cursor-pointer">清除所有筛选</button>
            </div>
        </div>
    `,
    data() {
        return {
            models: [],
            loading: true,
            sortBy: 'downloads',
            selectedTags: [],
        };
    },
    computed: {
        allTags() {
            const s = new Set();
            this.models.forEach(m => (m.tags || []).forEach(t => s.add(t)));
            return [...s];
        },
        filteredModels() {
            let list = [...this.models];
            // keyword
            if (this.searchKeyword) {
                const kw = this.searchKeyword.toLowerCase();
                list = list.filter(m => m.title.toLowerCase().includes(kw) || (m.tags || []).some(t => t.includes(kw)));
            }
            // tags
            if (this.selectedTags.length > 0) {
                list = list.filter(m => this.selectedTags.some(t => (m.tags || []).includes(t)));
            }
            // sort
            list.sort((a, b) => (b[this.sortBy] || 0) - (a[this.sortBy] || 0));
            return list;
        }
    },
    methods: {
        toggleTag(tag) {
            const i = this.selectedTags.indexOf(tag);
            if (i >= 0) this.selectedTags.splice(i, 1);
            else this.selectedTags.push(tag);
        },
        clearFilters() {
            this.selectedTags = [];
        },
        async loadModels() {
            this.loading = true;
            const res = await ApiService.getModels();
            if (res.code === 0) this.models = res.data;
            this.loading = false;
        }
    },
    created() { this.loadModels(); }
};

// ===== 2. 详情页 (含编辑) =====
const DetailView = {
    components: { AppIcon: window.AppComponents.AppIcon },
    template: `
        <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full flex-grow">
            <!-- Back -->
            <button @click="$router.push('/')"
                    class="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 hover:text-primary transition-colors mb-6 group cursor-pointer">
                <AppIcon name="arrow-left" :size="16" />
                返回模型库
            </button>

            <!-- Loading -->
            <div v-if="loading" class="flex items-center justify-center py-20">
                <div class="w-10 h-10 border-[3px] border-primary border-t-transparent rounded-full animate-spin"></div>
            </div>

            <!-- Content -->
            <div v-else-if="model"
                 class="bg-white dark:bg-dCard rounded-2xl overflow-hidden shadow-ambient-lg">

                <div class="grid grid-cols-1 lg:grid-cols-2 gap-0">
                    <!-- Left: Image -->
                    <div class="aspect-square lg:aspect-auto lg:min-h-[480px] bg-surfaceLow dark:bg-slate-900
                                flex items-center justify-center
                                border-b lg:border-b-0 lg:border-r border-surfaceHigh dark:border-dBorder">
                        <AppIcon name="box" :size="72" class="text-slate-300 dark:text-slate-700" />
                    </div>

                    <!-- Right: Info -->
                    <div class="p-6 lg:p-10 flex flex-col">
                        <!-- Title row -->
                        <div class="flex justify-between items-start gap-4 mb-5">
                            <h1 v-if="!editing" class="text-2xl lg:text-3xl font-extrabold leading-tight">{{ model.title }}</h1>
                            <input v-else v-model="form.title"
                                   class="text-2xl font-bold w-full bg-transparent border-b-2 border-primary py-1 text-onSurface dark:text-white" />
                            <button @click="toggleEdit"
                                    class="shrink-0 p-2.5 rounded-lg transition-colors cursor-pointer
                                           hover:bg-primary/10 text-slate-400 hover:text-primary"
                                    :title="editing ? '保存修改' : '编辑'"
                                    :aria-label="editing ? '保存修改' : '编辑'">
                                <AppIcon :name="editing ? 'check' : 'pen-line'" :size="20" />
                            </button>
                        </div>

                        <!-- Author -->
                        <div class="flex items-center gap-3 mb-6">
                            <div class="w-9 h-9 rounded-full bg-primary/15 text-primary font-bold flex items-center justify-center">
                                {{ (model.author||'?').charAt(0) }}
                            </div>
                            <span v-if="!editing" class="font-medium">{{ model.author }}</span>
                            <input v-else v-model="form.author"
                                   class="font-medium bg-transparent border-b border-slate-300 dark:border-slate-600 focus:border-primary px-1 text-onSurface dark:text-white" />
                        </div>

                        <!-- Stats -->
                        <div class="flex flex-wrap gap-3 mb-8">
                            <div class="flex items-center gap-1.5 text-sm bg-surfaceLow dark:bg-dBg px-3.5 py-2 rounded-lg">
                                <AppIcon name="download" :size="15" class="text-primary" />
                                <span class="font-semibold">{{ model.downloads }}</span>
                                <span class="text-slate-500 text-xs ml-0.5">次下载</span>
                            </div>
                            <div class="flex items-center gap-1.5 text-sm bg-surfaceLow dark:bg-dBg px-3.5 py-2 rounded-lg">
                                <AppIcon name="heart" :size="15" class="text-red-400" />
                                <span class="font-semibold">{{ model.likes }}</span>
                                <span class="text-slate-500 text-xs ml-0.5">收藏</span>
                            </div>
                        </div>

                        <!-- Tags -->
                        <div v-if="model.tags && model.tags.length" class="flex flex-wrap gap-2 mb-6">
                            <span v-for="tag in model.tags" :key="tag"
                                  class="tag-chip bg-surfaceTop dark:bg-dBorder text-slate-600 dark:text-slate-300">
                                {{ tag }}
                            </span>
                        </div>

                        <!-- Description -->
                        <div class="mb-3 font-semibold text-sm text-slate-500 dark:text-slate-400 uppercase tracking-wider">详细描述</div>
                        <p v-if="!editing"
                           class="text-slate-600 dark:text-slate-400 leading-relaxed text-sm whitespace-pre-line flex-grow">
                            {{ model.description }}
                        </p>
                        <textarea v-else v-model="form.description" rows="5"
                                  class="w-full text-sm bg-surfaceLow dark:bg-dBg rounded-lg p-3 resize-y
                                         text-slate-600 dark:text-slate-300 border border-surfaceHigh dark:border-dBorder">
                        </textarea>

                        <!-- Actions -->
                        <div class="mt-8 pt-6 border-t border-surfaceHigh dark:border-dBorder flex flex-col sm:flex-row gap-3">
                            <button @click="openFolder"
                                    class="flex-1 btn-primary-gradient py-2.5 rounded-lg font-medium
                                           flex justify-center items-center gap-2 cursor-pointer">
                                <AppIcon name="folder-open" :size="18" />
                                打开文件夹
                            </button>
                            <button v-if="model.source_url"
                                    class="flex-1 py-2.5 rounded-lg font-medium
                                           bg-surfaceLow dark:bg-dBg
                                           hover:bg-surfaceHigh dark:hover:bg-dBorder
                                           transition-colors cursor-pointer
                                           flex justify-center items-center gap-2">
                                <AppIcon name="external-link" :size="18" />
                                查看源文件
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Not Found -->
            <div v-else class="text-center py-20 text-slate-500">
                <p class="text-lg font-medium">模型未找到</p>
            </div>
        </div>
    `,
    data() {
        return {
            model: null,
            loading: true,
            editing: false,
            form: { title: '', author: '', description: '' },
        };
    },
    async created() {
        const id = this.$route.params.id;
        const res = await ApiService.getModelDetail(id);
        if (res.code === 0) {
            this.model = res.data;
            this.form = { title: res.data.title, author: res.data.author, description: res.data.description };
        }
        this.loading = false;
    },
    methods: {
        async toggleEdit() {
            if (this.editing) {
                const res = await ApiService.updateModel(this.model.id, this.form);
                if (res.code === 0) {
                    this.model = res.data;
                    this.$root.$refs.toast?.show('修改已保存');
                }
            } else {
                this.form = { title: this.model.title, author: this.model.author, description: this.model.description };
            }
            this.editing = !this.editing;
        },
        async openFolder() {
            await ApiService.openFolder(this.model.id);
            this.$root.$refs.toast?.show('已发送打开请求');
        }
    }
};

// ===== 3. 设置页 =====
const ConfigView = {
    components: { AppIcon: window.AppComponents.AppIcon },
    template: `
        <div class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full flex-grow">
            <h1 class="text-3xl font-extrabold tracking-tight mb-8">设置</h1>

            <!-- Loading -->
            <div v-if="loading" class="space-y-6">
                <div class="h-48 skeleton"></div>
                <div class="h-32 skeleton"></div>
            </div>

            <!-- Content -->
            <div v-else class="bg-white dark:bg-dCard rounded-2xl overflow-hidden shadow-ambient">
                <div class="p-6 lg:p-8 space-y-8">

                    <!-- Storage -->
                    <section>
                        <h2 class="text-base font-semibold flex items-center gap-2 mb-4">
                            <span class="w-7 h-7 rounded-lg bg-primary/15 flex items-center justify-center">
                                <AppIcon name="folder-tree" :size="16" class="text-primary" />
                            </span>
                            存储配置
                        </h2>
                        <div class="space-y-4">
                            <div>
                                <label for="cfgDataPath" class="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1.5">档案数据路径</label>
                                <div class="flex gap-2">
                                    <input id="cfgDataPath" type="text" v-model="config.download_dir"
                                           class="flex-1 bg-surfaceLow dark:bg-dInput rounded-lg px-3 py-2.5 text-sm
                                                  border border-outlineVar/20 dark:border-dBorder
                                                  focus:border-primary transition-colors">
                                    <button class="px-4 py-2.5 text-sm font-medium rounded-lg
                                                   bg-surfaceLow dark:bg-dBg hover:bg-surfaceHigh dark:hover:bg-dBorder
                                                   transition-colors cursor-pointer whitespace-nowrap">
                                        浏览
                                    </button>
                                </div>
                                <p class="mt-1.5 text-xs text-slate-500">保存模型和索引文件的根目录。</p>
                            </div>

                            <div>
                                <label for="cfgCookiePath" class="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1.5">Cookie 文件路径</label>
                                <input id="cfgCookiePath" type="text" v-model="config.cookie_file"
                                       class="w-full bg-surfaceLow dark:bg-dInput rounded-lg px-3 py-2.5 text-sm
                                              border border-outlineVar/20 dark:border-dBorder
                                              focus:border-primary transition-colors">
                            </div>
                        </div>
                    </section>

                    <hr class="border-surfaceHigh dark:border-dBorder">

                    <!-- Import -->
                    <section>
                        <h2 class="text-base font-semibold flex items-center gap-2 mb-4">
                            <span class="w-7 h-7 rounded-lg bg-primary/15 flex items-center justify-center">
                                <AppIcon name="hard-drive-download" :size="16" class="text-primary" />
                            </span>
                            本地导入
                        </h2>
                        <div class="space-y-4">
                            <label class="flex items-center justify-between cursor-pointer group">
                                <div>
                                    <p class="text-sm font-medium group-hover:text-primary transition-colors">启用本地批量导入</p>
                                    <p class="text-xs text-slate-500 mt-0.5">自动扫描 watch 文件夹中的新模型文件。</p>
                                </div>
                                <div class="relative">
                                    <input type="checkbox" v-model="config.local_batch_import.enabled" class="sr-only peer">
                                    <div class="w-11 h-6 bg-surfaceTop dark:bg-dBorder rounded-full
                                                peer-checked:bg-primary transition-colors duration-200"></div>
                                    <div class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow
                                                peer-checked:translate-x-5 transition-transform duration-200"></div>
                                </div>
                            </label>

                            <div v-if="config.local_batch_import.enabled">
                                <label class="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1.5">扫描间隔 (秒)</label>
                                <input type="number" v-model.number="config.local_batch_import.scan_interval_seconds"
                                       class="w-32 bg-surfaceLow dark:bg-dInput rounded-lg px-3 py-2.5 text-sm
                                              border border-outlineVar/20 dark:border-dBorder focus:border-primary transition-colors">
                            </div>
                        </div>
                    </section>

                    <hr class="border-surfaceHigh dark:border-dBorder">

                    <!-- Notifications -->
                    <section>
                        <h2 class="text-base font-semibold flex items-center gap-2 mb-4">
                            <span class="w-7 h-7 rounded-lg bg-primary/15 flex items-center justify-center">
                                <AppIcon name="bell" :size="16" class="text-primary" />
                            </span>
                            通知推送
                        </h2>
                        <div class="space-y-4">
                            <label class="flex items-center justify-between cursor-pointer group">
                                <div>
                                    <p class="text-sm font-medium group-hover:text-primary transition-colors">Telegram 推送</p>
                                    <p class="text-xs text-slate-500 mt-0.5">新模型归档完成时通过 Telegram Bot 推送通知。</p>
                                </div>
                                <div class="relative">
                                    <input type="checkbox" v-model="config.notifications.telegram.enable_push" class="sr-only peer">
                                    <div class="w-11 h-6 bg-surfaceTop dark:bg-dBorder rounded-full
                                                peer-checked:bg-primary transition-colors duration-200"></div>
                                    <div class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow
                                                peer-checked:translate-x-5 transition-transform duration-200"></div>
                                </div>
                            </label>

                            <label class="flex items-center justify-between cursor-pointer group">
                                <div>
                                    <p class="text-sm font-medium group-hover:text-primary transition-colors">企业微信推送</p>
                                    <p class="text-xs text-slate-500 mt-0.5">通过企业微信应用发送归档通知。</p>
                                </div>
                                <div class="relative">
                                    <input type="checkbox" v-model="config.notifications.wecom.enable_push" class="sr-only peer">
                                    <div class="w-11 h-6 bg-surfaceTop dark:bg-dBorder rounded-full
                                                peer-checked:bg-primary transition-colors duration-200"></div>
                                    <div class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow
                                                peer-checked:translate-x-5 transition-transform duration-200"></div>
                                </div>
                            </label>
                        </div>
                    </section>
                </div>

                <!-- Footer Actions -->
                <div class="bg-surfaceLow dark:bg-dBg/50 p-6 flex justify-end gap-3 border-t border-surfaceHigh dark:border-dBorder">
                    <button @click="$router.push('/')"
                            class="px-5 py-2.5 text-sm font-medium rounded-lg
                                   bg-white dark:bg-dCard
                                   border border-surfaceHigh dark:border-dBorder
                                   hover:bg-surfaceHigh dark:hover:bg-dBorder
                                   transition-colors cursor-pointer">
                        取消
                    </button>
                    <button @click="save"
                            class="px-5 py-2.5 text-sm font-medium rounded-lg
                                   btn-primary-gradient cursor-pointer
                                   flex items-center gap-2"
                            :disabled="saving">
                        <AppIcon v-if="saving" name="loader-2" :size="16" class="animate-spin" />
                        <AppIcon v-else name="save" :size="16" />
                        保存更改
                    </button>
                </div>
            </div>
        </div>
    `,
    data() {
        return {
            loading: true,
            saving: false,
            config: {
                download_dir: '',
                cookie_file: '',
                logs_dir: '',
                local_batch_import: { enabled: true, scan_interval_seconds: 30 },
                notifications: {
                    telegram: { enable_push: false },
                    wecom: { enable_push: false }
                },
                folder_open: { enabled: true, open_mode: 'client' }
            }
        };
    },
    async created() {
        const res = await ApiService.getConfig();
        if (res.code === 0) {
            // 稳健地合并远端配置，避免结构缺失
            this.config = {
                ...this.config,
                ...res.data,
                local_batch_import: { ...this.config.local_batch_import, ...(res.data.local_batch_import || {}) },
                notifications: {
                    telegram: { ...this.config.notifications.telegram, ...(res.data.notifications?.telegram || {}) },
                    wecom: { ...this.config.notifications.wecom, ...(res.data.notifications?.wecom || {}) }
                }
            };
        }
        this.loading = false;
    },
    methods: {
        async save() {
            this.saving = true;
            const res = await ApiService.saveConfig(this.config);
            this.saving = false;
            if (res.code === 0) {
                this.$root.$refs.toast?.show('设置保存成功');
            } else {
                this.$root.$refs.toast?.show('保存失败: ' + res.message, 'error');
            }
        }
    }
};

window.AppViews = { HomeView, DetailView, ConfigView };
})();
