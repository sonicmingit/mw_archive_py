(() => {
const { ref, reactive, computed, onMounted, watch } = Vue;

function sourceOptions() {
    return [
        { id: 'all', label: '全部' },
        { id: 'mw_cn', label: 'MakerWorld 国内' },
        { id: 'mw_global', label: 'MakerWorld 国际' },
        { id: 'localmodel', label: '手动导入' },
        { id: 'others', label: '其他来源' }
    ];
}

const HomeView = {
    components: {
        AppIcon: window.AppComponents.AppIcon,
        LibrarySidebar: window.AppComponents.LibrarySidebar,
        ModelCard: window.AppComponents.ModelCard
    },
    props: ['searchKeyword'],
    template: `
        <div class="app-shell flex gap-5 p-5">
            <LibrarySidebar
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

            <main class="app-main min-w-0 flex-1 space-y-5">
                <section class="glass-dark rounded-[28px] border border-borderSoft px-5 py-4">
                    <div class="flex flex-wrap items-center justify-between gap-4">
                        <div>
                            <h1 class="text-2xl font-extrabold">本地模型库</h1>
                            <p class="mt-1 text-sm text-textMuted">共 {{ filteredModels.length }} 个模型</p>
                        </div>
                        <div class="flex flex-wrap items-center gap-2">
                            <button type="button" class="pill-btn inline-flex items-center gap-2 rounded-2xl px-4 py-2.5"
                                :class="batchMode ? 'is-active' : ''" @click="toggleBatchMode">
                                <AppIcon name="check-square" :size="16" />多选
                            </button>
                            <button type="button" class="pill-btn inline-flex items-center gap-2 rounded-2xl px-4 py-2.5"
                                :class="compactMode ? 'is-active' : ''" @click="compactMode = !compactMode">
                                <AppIcon name="minimize-2" :size="16" />简洁模式
                            </button>
                            <select v-model="sortBy" class="select-dark !w-auto !rounded-2xl !py-2.5">
                                <option value="archivedDate">采集时间倒序</option>
                                <option value="publishDate">发布时间倒序</option>
                                <option value="downloads">下载量</option>
                                <option value="favorites">收藏数</option>
                            </select>
                            <button type="button" class="secondary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-2.5" @click="reloadLibrary">
                                <AppIcon name="refresh-cw" :size="16" />刷新
                            </button>
                        </div>
                    </div>

                    <transition name="modal-fade">
                        <div v-if="batchMode" class="mt-4 rounded-[22px] border border-cyan/20 bg-cyan/10 p-4">
                            <div class="flex flex-wrap items-center justify-between gap-3">
                                <div class="text-sm font-semibold text-cyan">已选 {{ selectedIds.length }} 项</div>
                                <div class="flex flex-wrap items-center gap-2">
                                    <button type="button" class="primary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-2.5"
                                        :disabled="!selectedIds.length" @click="openFolderModal">
                                        <AppIcon name="folder-heart" :size="16" />批量收藏
                                    </button>
                                    <button type="button" class="secondary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-2.5"
                                        :disabled="!selectedIds.length" @click="clearSelection">
                                        <AppIcon name="x" :size="16" />清空选择
                                    </button>
                                </div>
                            </div>
                        </div>
                    </transition>
                </section>

                <section>
                    <div v-if="filteredModels.length" class="card-grid" :class="{ compact: compactMode }">
                        <ModelCard
                            v-for="model in filteredModels"
                            :key="model.id"
                            :model="model"
                            :compact="compactMode"
                            :batch-mode="batchMode"
                            :selected="selectedIds.includes(model.id)"
                            @open="openDetail"
                            @toggle-select="toggleSelection"
                            @toggle-favorite="toggleFavorite"
                        />
                    </div>
                    <div v-else class="section-card flex min-h-[300px] items-center justify-center p-10 text-center">
                        <div>
                            <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-panelSoft text-textMuted">
                                <AppIcon name="search-x" :size="28" />
                            </div>
                            <h3 class="text-xl font-semibold">没有匹配的模型</h3>
                            <p class="mt-2 text-sm text-textMuted">可以调整搜索词或取消侧栏筛选。</p>
                        </div>
                    </div>
                </section>

                <transition name="modal-fade">
                    <div v-if="folderModalOpen" class="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 px-4">
                        <div class="w-full max-w-2xl rounded-[28px] border border-borderStrong bg-panel shadow-glow">
                            <div class="flex items-center justify-between border-b border-borderSoft px-6 py-5">
                                <div>
                                    <div class="text-2xl font-bold">批量收藏</div>
                                    <div class="mt-1 text-sm text-textMuted">已选 {{ selectedIds.length }} 个模型</div>
                                </div>
                                <button type="button" class="secondary-btn inline-flex h-10 w-10 items-center justify-center rounded-2xl" @click="folderModalOpen = false">
                                    <AppIcon name="x" :size="18" />
                                </button>
                            </div>
                            <div class="grid gap-6 px-6 py-6 md:grid-cols-2">
                                <div>
                                    <div class="mb-3 text-sm font-semibold text-cyan">已有收藏夹</div>
                                    <div class="space-y-2">
                                        <button v-for="folder in store.folders" :key="folder.id" type="button"
                                            class="w-full rounded-2xl border px-4 py-3 text-left transition"
                                            :class="folderDraft.id === folder.id ? 'border-cyan bg-cyan/10 text-cyan' : 'border-borderSoft bg-panelSoft hover:border-borderStrong'"
                                            @click="pickFolder(folder)">
                                            <div class="font-semibold">{{ folder.name }}</div>
                                            <div class="mt-1 text-xs text-textMuted">{{ folder.description || '无简介' }}</div>
                                        </button>
                                    </div>
                                </div>
                                <div class="space-y-3">
                                    <div class="text-sm font-semibold text-cyan">新建 / 编辑</div>
                                    <input v-model="folderDraft.name" class="input-dark" placeholder="收藏夹名称">
                                    <textarea v-model="folderDraft.description" rows="4" class="textarea-dark" placeholder="收藏夹说明"></textarea>
                                    <button type="button" class="primary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="saveFolder">
                                        <AppIcon name="save" :size="16" />保存并加入已选模型
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </transition>
            </main>
        </div>
    `,
    setup(props) {
        const router = VueRouter.useRouter();
        const store = reactive({ models: [], folders: [] });
        const filters = reactive({ source: 'all', folder: '', category: '', favoritesOnly: false, printedOnly: false });
        const batchMode = ref(false);
        const compactMode = ref(false);
        const sortBy = ref('archivedDate');
        const selectedIds = ref([]);
        const folderModalOpen = ref(false);
        const folderDraft = reactive({ id: '', name: '', description: '' });

        async function loadLibrary() {
            const res = await ApiService.getLibrary();
            if (res.code === 0) {
                store.models = res.data.models;
                store.folders = res.data.folders;
            }
        }

        const categories = computed(() => [...new Set(store.models.map((item) => item.category).filter(Boolean))]);
        const sidebarSources = computed(() => sourceOptions().map((option) => ({
            ...option,
            count: option.id === 'all' ? store.models.length : store.models.filter((item) => item.source === option.id).length
        })));
        const filteredModels = computed(() => {
            let list = [...store.models];
            const search = String(props.searchKeyword || '').toLowerCase();
            if (search) list = list.filter((item) => item.title.toLowerCase().includes(search) || item.tags.some((tag) => tag.toLowerCase().includes(search)));
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

        function openDetail(id) { router.push(`/detail/${id}`); }
        function toggleBatchMode() { batchMode.value = !batchMode.value; if (!batchMode.value) selectedIds.value = []; }
        function toggleSelection(id) { const next = new Set(selectedIds.value); if (next.has(id)) next.delete(id); else next.add(id); selectedIds.value = [...next]; }
        function clearSelection() { selectedIds.value = []; }
        async function toggleFavorite(id) { await ApiService.toggleFavorite(id); await loadLibrary(); }
        function openFolderModal() { folderDraft.id = ''; folderDraft.name = ''; folderDraft.description = ''; folderModalOpen.value = true; }
        function pickFolder(folder) { folderDraft.id = folder.id; folderDraft.name = folder.name; folderDraft.description = folder.description || ''; }
        async function saveFolder() {
            if (!folderDraft.name.trim()) return;
            const res = await ApiService.saveFolder(folderDraft, selectedIds.value);
            if (res.code === 0) { folderModalOpen.value = false; selectedIds.value = []; await loadLibrary(); }
        }
        async function reloadLibrary() { await loadLibrary(); }

        onMounted(loadLibrary);
        return { store, filters, categories, sidebarSources, batchMode, compactMode, sortBy, selectedIds, filteredModels, openDetail, toggleBatchMode, toggleSelection, clearSelection, toggleFavorite, folderModalOpen, folderDraft, openFolderModal, pickFolder, saveFolder, reloadLibrary };
    }
};

const DetailView = {
    components: { AppIcon: window.AppComponents.AppIcon },
    template: `
        <div class="mx-auto max-w-[1600px] p-5">
            <button type="button" class="mb-4 inline-flex items-center gap-2 text-sm text-textMuted transition hover:text-white" @click="$router.push('/')">
                <AppIcon name="arrow-left" :size="16" />返回模型库
            </button>
            <div v-if="loading" class="section-card flex min-h-[420px] items-center justify-center">
                <div class="h-12 w-12 animate-spin rounded-full border-[3px] border-cyan border-t-transparent"></div>
            </div>
            <div v-else-if="model" class="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_420px]">
                <section class="space-y-5">
                    <div class="section-card overflow-hidden p-3">
                        <div class="overflow-hidden rounded-[22px] bg-panelSoft">
                            <img :src="activeImage" :alt="model.title" class="h-[420px] w-full object-cover md:h-[560px]">
                        </div>
                        <div class="mt-3 flex gap-3 overflow-auto">
                            <button v-for="image in model.images" :key="image" type="button" class="h-20 w-24 shrink-0 overflow-hidden rounded-2xl border transition"
                                :class="activeImage === image ? 'border-cyan' : 'border-borderSoft'" @click="activeImage = image">
                                <img :src="image" class="h-full w-full object-cover">
                            </button>
                        </div>
                    </div>
                    <div class="section-card p-6">
                        <div class="mb-4 flex items-center gap-2 text-cyan text-sm font-semibold"><AppIcon name="file-text" :size="16" />模型简介</div>
                        <div class="text-sm leading-7 text-zinc-300" v-html="model.description"></div>
                    </div>
                    <div class="section-card p-6">
                        <div class="mb-4 flex items-center justify-between gap-3">
                            <div class="flex items-center gap-2 text-cyan text-sm font-semibold"><AppIcon name="layers-3" :size="16" />打印配置</div>
                            <button type="button" class="primary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-2.5" @click="showAddProfile = true">
                                <AppIcon name="plus" :size="16" />添加打印配置
                            </button>
                        </div>
                        <div class="space-y-4">
                            <article v-for="profile in model.printProfiles" :key="profile.id" class="rounded-[22px] border border-borderSoft bg-panelSoft p-5">
                                <div class="flex flex-wrap items-start justify-between gap-4">
                                    <div>
                                        <h3 class="text-xl font-bold">{{ profile.name }}</h3>
                                        <p class="mt-2 text-sm text-textMuted">{{ profile.summary }}</p>
                                        <div class="mt-3 flex flex-wrap gap-2 text-xs text-textMuted">
                                            <span class="tag-chip">{{ profile.plates }} 盘</span>
                                            <span class="tag-chip">{{ profile.duration }}</span>
                                            <span class="tag-chip">{{ profile.totalWeight }} g</span>
                                        </div>
                                    </div>
                                    <div class="flex flex-wrap gap-2">
                                        <button type="button" class="red-btn inline-flex items-center gap-2 rounded-2xl px-4 py-2.5" @click="openPlateModal(profile)">
                                            <AppIcon name="files" :size="16" />详情
                                        </button>
                                        <button type="button" class="primary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-2.5" @click="printProfile(profile)">
                                            <AppIcon name="printer" :size="16" />打印
                                        </button>
                                        <button type="button" class="green-btn inline-flex items-center gap-2 rounded-2xl px-4 py-2.5" @click="previewProfile(profile)">
                                            <AppIcon name="eye" :size="16" />预览
                                        </button>
                                    </div>
                                </div>
                                <div class="mt-4 flex flex-wrap gap-3">
                                    <div v-for="material in profile.materials" :key="material.type + material.color" class="tag-chip !rounded-2xl !px-3 !py-2">
                                        <span class="mr-2 inline-block h-3 w-3 rounded-full align-middle" :style="{ backgroundColor: material.color }"></span>
                                        {{ material.type }} {{ material.weight }} g
                                    </div>
                                </div>
                                <div v-if="profile.previewImages && profile.previewImages.length" class="mt-4 flex gap-3 overflow-auto">
                                    <img v-for="image in profile.previewImages" :key="image" :src="image" class="h-24 w-32 rounded-2xl object-cover">
                                </div>
                            </article>
                            <div v-if="!model.printProfiles.length" class="rounded-[22px] border border-dashed border-borderStrong p-8 text-center text-sm text-textMuted">当前还没有打印配置，点击右上角按钮新增。</div>
                        </div>
                    </div>
                </section>
                <aside class="space-y-5">
                    <div class="section-card p-6">
                        <div class="flex items-start justify-between gap-4">
                            <div>
                                <h1 class="text-[30px] font-extrabold leading-tight">{{ model.title }}</h1>
                                <div class="mt-4 flex items-center gap-3 text-sm text-zinc-300">
                                    <div class="flex h-10 w-10 items-center justify-center rounded-full bg-cyan/15 font-bold text-cyan">{{ (model.author || '?').slice(0, 1) }}</div>
                                    <div><div class="font-semibold text-white">{{ model.author }}</div><div class="text-textMuted">{{ model.category }}</div></div>
                                </div>
                            </div>
                            <button type="button" class="secondary-btn inline-flex h-11 w-11 items-center justify-center rounded-2xl" @click="toggleFavorite">
                                <AppIcon name="heart" :size="18" :class="model.isFavorited ? 'text-amber-400' : 'text-textMuted'" />
                            </button>
                        </div>
                        <div class="mt-5 flex flex-wrap gap-2">
                            <span class="source-chip"><AppIcon name="globe-2" :size="14" />{{ model.sourceLabel }}</span>
                            <span class="source-chip secondary"><AppIcon name="bookmark" :size="14" />{{ model.sourceMark || '未标记' }}</span>
                            <a v-if="model.sourceUrl" :href="model.sourceUrl" target="_blank" rel="noreferrer" class="source-chip secondary no-underline">
                                <AppIcon name="external-link" :size="14" />来源链接
                            </a>
                        </div>
                        <div class="mt-5 grid grid-cols-2 gap-3">
                            <div class="stat-tile"><div class="text-sm text-textMuted">点赞</div><div class="mt-2 text-2xl font-bold">{{ model.likes }}</div></div>
                            <div class="stat-tile"><div class="text-sm text-textMuted">收藏</div><div class="mt-2 text-2xl font-bold">{{ model.favorites }}</div></div>
                            <div class="stat-tile"><div class="text-sm text-textMuted">打印</div><div class="mt-2 text-2xl font-bold">{{ model.prints }}</div></div>
                            <div class="stat-tile"><div class="text-sm text-textMuted">下载</div><div class="mt-2 text-2xl font-bold">{{ model.downloads }}</div></div>
                        </div>
                    </div>
                    <div class="section-card p-6">
                        <div class="mb-4 flex items-center justify-between gap-3">
                            <div class="flex items-center gap-2 text-cyan text-sm font-semibold"><AppIcon name="badge-info" :size="16" />来源标记</div>
                            <button type="button" class="secondary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-2.5" @click="showSourceEditor = true">
                                <AppIcon name="pen-line" :size="16" />编辑
                            </button>
                        </div>
                        <div class="space-y-3 text-sm">
                            <div class="rounded-2xl border border-borderSoft bg-panelSoft p-4"><div class="text-textMuted">来源类型</div><div class="mt-2 font-semibold">{{ model.sourceLabel }}</div></div>
                            <div class="rounded-2xl border border-borderSoft bg-panelSoft p-4"><div class="text-textMuted">标记说明</div><div class="mt-2 font-semibold">{{ model.sourceMark || '暂无' }}</div></div>
                        </div>
                    </div>
                    <div class="section-card p-6">
                        <div class="mb-4 flex items-center gap-2 text-cyan text-sm font-semibold"><AppIcon name="tags" :size="16" />标签</div>
                        <div class="flex flex-wrap gap-2"><span v-for="tag in model.tags" :key="tag" class="tag-chip">{{ tag }}</span></div>
                    </div>
                    <div class="section-card p-6">
                        <div class="mb-4 flex items-center gap-2 text-cyan text-sm font-semibold"><AppIcon name="paperclip" :size="16" />附件文件</div>
                        <div class="space-y-3">
                            <div v-for="attachment in model.attachments" :key="attachment.id" class="flex items-center justify-between rounded-2xl border border-borderSoft bg-panelSoft p-4">
                                <div><div class="font-semibold">{{ attachment.name }}</div><div class="mt-1 text-xs text-textMuted">{{ attachment.type }} · {{ attachment.size }}</div></div>
                                <button type="button" class="secondary-btn rounded-2xl px-3 py-2 text-sm" @click="downloadAttachment(attachment)">下载</button>
                            </div>
                            <div v-if="!model.attachments.length" class="rounded-2xl border border-dashed border-borderStrong p-4 text-sm text-textMuted">暂无附件</div>
                        </div>
                    </div>
                </aside>
            </div>

            <transition name="modal-fade">
                <div v-if="showSourceEditor" class="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 px-4">
                    <div class="w-full max-w-2xl rounded-[28px] border border-borderStrong bg-panel shadow-glow">
                        <div class="flex items-center justify-between border-b border-borderSoft px-6 py-5">
                            <div class="text-2xl font-bold">编辑来源标记</div>
                            <button type="button" class="secondary-btn inline-flex h-10 w-10 items-center justify-center rounded-2xl" @click="showSourceEditor = false">
                                <AppIcon name="x" :size="18" />
                            </button>
                        </div>
                        <div class="space-y-4 px-6 py-6">
                            <select v-model="sourceForm.source" class="select-dark">
                                <option v-for="option in sourceList" :key="option.id" :value="option.id">{{ option.label }}</option>
                            </select>
                            <input v-model="sourceForm.sourceUrl" class="input-dark" placeholder="来源链接">
                            <textarea v-model="sourceForm.sourceMark" rows="4" class="textarea-dark" placeholder="来源标记说明"></textarea>
                            <button type="button" class="primary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="saveSourceMark">
                                <AppIcon name="save" :size="16" />保存来源标记
                            </button>
                        </div>
                    </div>
                </div>
            </transition>

            <transition name="modal-fade">
                <div v-if="showAddProfile" class="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 px-4">
                    <div class="w-full max-w-3xl rounded-[28px] border border-borderStrong bg-panel shadow-glow">
                        <div class="flex items-center justify-between border-b border-borderSoft px-6 py-5">
                            <div class="text-2xl font-bold">添加打印配置</div>
                            <button type="button" class="secondary-btn inline-flex h-10 w-10 items-center justify-center rounded-2xl" @click="showAddProfile = false">
                                <AppIcon name="x" :size="18" />
                            </button>
                        </div>
                        <div class="grid gap-4 px-6 py-6 md:grid-cols-2">
                            <div class="md:col-span-2">
                                <input type="file" accept=".3mf" class="input-dark" @change="onProfileFileChange">
                            </div>
                            <input v-model="profileForm.name" class="input-dark" placeholder="配置标题，可选">
                            <div class="input-dark flex items-center text-sm text-textMuted">{{ profileForm.fileName || '未选择 3MF 文件' }}</div>
                            <div class="md:col-span-2"><textarea v-model="profileForm.summary" rows="4" class="textarea-dark" placeholder="配置说明，可选"></textarea></div>
                            <div class="md:col-span-2">
                                <button type="button" class="primary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="addProfile">
                                    <AppIcon name="plus" :size="16" />保存配置
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </transition>

            <transition name="modal-fade">
                <div v-if="plateModal.profile" class="fixed inset-0 z-[95] flex items-center justify-center bg-black/75 px-4">
                    <div class="grid max-h-[90vh] w-full max-w-6xl overflow-hidden rounded-[28px] border border-borderStrong bg-panel shadow-glow lg:grid-cols-[1fr_420px]">
                        <div class="flex items-center justify-center bg-[#1b1b1b] p-8">
                            <img :src="plateModal.activeImage" class="max-h-[70vh] rounded-[26px] object-contain">
                        </div>
                        <div class="overflow-auto border-l border-borderSoft">
                            <div class="flex items-center justify-between border-b border-borderSoft px-6 py-5">
                                <div class="text-2xl font-bold">分盘详情</div>
                                <button type="button" class="secondary-btn inline-flex h-10 w-10 items-center justify-center rounded-2xl" @click="closePlateModal">
                                    <AppIcon name="x" :size="18" />
                                </button>
                            </div>
                            <div class="space-y-4 px-6 py-6">
                                <article v-for="plate in plateModal.profile.platesDetail" :key="plate.id" class="cursor-pointer rounded-[22px] border p-4 transition"
                                    :class="plateModal.activePlateId === plate.id ? 'border-cyan bg-panelHard' : 'border-borderSoft bg-panelSoft'" @click="selectPlate(plate)">
                                    <div class="text-2xl font-bold">{{ plate.name }}</div>
                                    <div class="mt-4 flex items-center gap-6 text-textMuted">
                                        <div class="inline-flex items-center gap-2"><AppIcon name="clock-3" :size="16" />{{ plate.time }}</div>
                                        <div class="inline-flex items-center gap-2"><AppIcon name="package" :size="16" />{{ plate.weight }}</div>
                                    </div>
                                    <div class="mt-4 tag-chip !inline-flex !rounded-2xl !px-3 !py-2">{{ plate.materialLabel }}</div>
                                </article>
                            </div>
                        </div>
                    </div>
                </div>
            </transition>
        </div>
    `,
    setup() {
        const route = VueRouter.useRoute();
        const router = VueRouter.useRouter();
        const loading = ref(true);
        const model = ref(null);
        const activeImage = ref('');
        const showSourceEditor = ref(false);
        const showAddProfile = ref(false);
        const sourceList = sourceOptions().filter((item) => item.id !== 'all');
        const sourceForm = reactive({ source: 'mw_cn', sourceUrl: '', sourceMark: '' });
        const profileForm = reactive({ name: '', summary: '', file: null, fileName: '' });
        const plateModal = reactive({ profile: null, activeImage: '', activePlateId: '' });

        async function loadDetail() {
            loading.value = true;
            const res = await ApiService.getModelDetail(route.params.id);
            loading.value = false;
            if (res.code !== 0) { router.push('/'); return; }
            model.value = res.data.model;
            activeImage.value = model.value.images[0] || model.value.coverImage;
            sourceForm.source = model.value.source;
            sourceForm.sourceUrl = model.value.sourceUrl || '';
            sourceForm.sourceMark = model.value.sourceMark || '';
        }

        async function toggleFavorite() { await ApiService.toggleFavorite(route.params.id); await loadDetail(); }
        async function saveSourceMark() {
            const res = await ApiService.updateSourceMark(route.params.id, sourceForm);
            if (res.code === 0) { showSourceEditor.value = false; await loadDetail(); }
        }
        async function addProfile() {
            if (!profileForm.file) return;
            const res = await ApiService.importPrintProfile(route.params.id, profileForm.file, profileForm.name, profileForm.summary);
            if (res.code === 0) {
                showAddProfile.value = false;
                profileForm.name = '';
                profileForm.summary = '';
                profileForm.file = null;
                profileForm.fileName = '';
                await loadDetail();
            }
        }
        function onProfileFileChange(event) {
            const file = event.target && event.target.files ? event.target.files[0] : null;
            profileForm.file = file || null;
            profileForm.fileName = file ? file.name : '';
        }
        function openPlateModal(profile) {
            plateModal.profile = profile;
            const firstPlate = profile.platesDetail && profile.platesDetail.length ? profile.platesDetail[0] : null;
            plateModal.activeImage = firstPlate ? firstPlate.previewImage : (profile.previewImages[0] || '');
            plateModal.activePlateId = firstPlate ? firstPlate.id : '';
        }
        function selectPlate(plate) { plateModal.activeImage = plate.previewImage; plateModal.activePlateId = plate.id; }
        function closePlateModal() { plateModal.profile = null; plateModal.activeImage = ''; plateModal.activePlateId = ''; }
        function printProfile(profile) { window.open(`/api/models/${encodeURIComponent(String(route.params.id || ''))}/instances/${profile.id}/download`, '_blank'); }
        function previewProfile(profile) { if (profile.previewImages && profile.previewImages.length) activeImage.value = profile.previewImages[0]; }
        function downloadAttachment(attachment) { if (attachment && attachment.url) window.open(attachment.url, '_blank'); }

        watch(() => route.params.id, loadDetail);
        onMounted(loadDetail);

        return { loading, model, activeImage, showSourceEditor, showAddProfile, sourceList, sourceForm, profileForm, plateModal, toggleFavorite, saveSourceMark, addProfile, onProfileFileChange, openPlateModal, selectPlate, closePlateModal, printProfile, previewProfile, downloadAttachment };
    }
};

const ConfigView = {
    components: { AppIcon: window.AppComponents.AppIcon },
    template: `
        <div class="mx-auto max-w-[1600px] p-5">
            <div v-if="loading" class="section-card flex min-h-[420px] items-center justify-center">
                <div class="h-12 w-12 animate-spin rounded-full border-[3px] border-cyan border-t-transparent"></div>
            </div>
            <div v-else class="space-y-5">
                <section class="section-card p-6">
                    <button type="button" class="inline-flex items-center gap-2 text-sm text-textMuted transition hover:text-white" @click="$router.push('/')">
                        <AppIcon name="arrow-left" :size="16" />返回模型库
                    </button>
                    <div class="mt-5 flex flex-wrap items-start justify-between gap-4">
                        <div>
                            <h1 class="text-3xl font-extrabold">控制台</h1>
                            <p class="mt-2 text-sm text-textMuted">系统设置与高级工具，布局按 Figma ConsoleSettings 组织。</p>
                        </div>
                        <div class="flex flex-wrap gap-3">
                            <div class="stat-tile min-w-[160px]">
                                <div class="text-sm text-textMuted">Cookie 组数</div>
                                <div class="mt-2 text-2xl font-bold">{{ totalCookieCount }}</div>
                            </div>
                            <div class="stat-tile min-w-[200px]">
                                <div class="text-sm text-textMuted">最近更新时间</div>
                                <div class="mt-2 text-sm font-semibold">{{ state.config.cookie_updated_at || '暂无' }}</div>
                            </div>
                        </div>
                    </div>
                </section>

                <div class="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
                <aside class="section-card overflow-hidden">
                    <button v-for="tab in tabs" :key="tab.id" type="button"
                        class="flex w-full items-center gap-3 border-l-4 px-5 py-4 text-left transition"
                        :class="activeTab === tab.id ? 'border-cyan bg-cyan/10 text-cyan' : 'border-transparent hover:bg-panelSoft'"
                        @click="activeTab = tab.id">
                        <AppIcon :name="tab.icon" :size="18" />
                        <span class="font-medium">{{ tab.label }}</span>
                    </button>
                </aside>

                <section class="section-card p-6">
                    <div v-if="activeTab === 'cookies'" class="space-y-6">
                        <div>
                            <h2 class="text-2xl font-bold">Cookie 配置</h2>
                            <p class="mt-1 text-sm text-textMuted">基础路径、Cookie 数量与原始内容编辑。</p>
                        </div>
                        <div class="grid gap-4 md:grid-cols-3">
                            <div class="stat-tile"><div class="text-sm text-textMuted">下载目录</div><div class="mt-2 break-all text-sm font-semibold">{{ state.config.download_dir }}</div></div>
                            <div class="stat-tile"><div class="text-sm text-textMuted">日志目录</div><div class="mt-2 break-all text-sm font-semibold">{{ state.config.logs_dir }}</div></div>
                            <div class="stat-tile"><div class="text-sm text-textMuted">Cookie 文件</div><div class="mt-2 break-all text-sm font-semibold">{{ state.config.cookie_file }}</div></div>
                        </div>
                        <div class="grid gap-4 md:grid-cols-2">
                            <div class="rounded-[22px] border border-borderSoft bg-panelSoft p-5">
                                <div class="flex items-start justify-between gap-3">
                                    <div>
                                        <div class="text-lg font-bold">MakerWorld 国内</div>
                                        <div class="mt-1 text-sm text-textMuted">当前已保存 {{ state.cookieCounts.cn }} 条 Cookie</div>
                                    </div>
                                    <span class="source-chip" :class="state.cookieCounts.cn ? '' : 'secondary'">
                                        <AppIcon :name="state.cookieCounts.cn ? 'badge-check' : 'circle-off'" :size="14" />
                                        {{ state.cookieCounts.cn ? '已配置' : '未配置' }}
                                    </span>
                                </div>
                                <textarea v-model="state.cookieStore.cn" rows="8" class="textarea-dark mt-4" placeholder="每行一个 Cookie"></textarea>
                            </div>
                            <div class="rounded-[22px] border border-borderSoft bg-panelSoft p-5">
                                <div class="flex items-start justify-between gap-3">
                                    <div>
                                        <div class="text-lg font-bold">MakerWorld 国际</div>
                                        <div class="mt-1 text-sm text-textMuted">当前已保存 {{ state.cookieCounts.global }} 条 Cookie</div>
                                    </div>
                                    <span class="source-chip" :class="state.cookieCounts.global ? '' : 'secondary'">
                                        <AppIcon :name="state.cookieCounts.global ? 'badge-check' : 'circle-off'" :size="14" />
                                        {{ state.cookieCounts.global ? '已配置' : '未配置' }}
                                    </span>
                                </div>
                                <textarea v-model="state.cookieStore.global" rows="8" class="textarea-dark mt-4" placeholder="每行一个 Cookie"></textarea>
                            </div>
                        </div>
                        <div class="grid gap-4 md:grid-cols-2">
                            <div class="rounded-[22px] border border-borderSoft bg-panelSoft p-5">
                                <div class="text-sm font-semibold text-cyan">多 Cookie 状态</div>
                                <div class="mt-2 text-sm text-textMuted">{{ state.config.multi_cookie_enabled ? '已启用轮询' : '当前为单 Cookie 模式' }}</div>
                            </div>
                            <div class="rounded-[22px] border border-borderSoft bg-panelSoft p-5">
                                <div class="text-sm font-semibold text-cyan">最后更新</div>
                                <div class="mt-2 text-sm text-textMuted">{{ state.config.cookie_updated_at || '暂无记录' }}</div>
                            </div>
                        </div>
                        <button type="button" class="primary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="saveCookies">
                            <AppIcon name="save" :size="16" />保存 Cookie
                        </button>
                    </div>

                    <div v-else-if="activeTab === 'archive'" class="space-y-6">
                        <div>
                            <h2 class="text-2xl font-bold">模型归档</h2>
                            <p class="mt-1 text-sm text-textMuted">输入 MakerWorld 链接并直接调用后端归档。</p>
                        </div>
                        <input v-model="state.archiveUrl" class="input-dark" placeholder="https://makerworld.com.cn/...">
                        <button type="button" class="primary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="startArchive">
                            <AppIcon name="download" :size="16" />开始归档
                        </button>
                    </div>

                    <div v-else-if="activeTab === 'missing'" class="space-y-6">
                        <div class="flex items-center justify-between gap-3">
                            <div>
                                <h2 class="text-2xl font-bold">缺失记录</h2>
                                <p class="mt-1 text-sm text-textMuted">重试下载缺失的 3MF 文件。</p>
                            </div>
                            <button type="button" class="secondary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="retryMissing">
                                <AppIcon name="refresh-cw" :size="16" />重新下载
                            </button>
                        </div>
                        <div v-if="state.missing.length" class="space-y-3">
                            <div v-for="item in state.missing" :key="item.time + item.base_name + item.inst_id" class="rounded-2xl border border-borderSoft bg-panelSoft p-4">
                                <div class="font-semibold">{{ item.base_name }}</div>
                                <div class="mt-2 text-sm text-textMuted">实例 {{ item.inst_id }} · {{ item.title || '未命名配置' }}</div>
                                <div class="mt-1 text-xs text-textMuted">{{ item.time }} · {{ item.status }}</div>
                            </div>
                        </div>
                        <div v-else class="rounded-2xl border border-dashed border-borderStrong p-6 text-sm text-textMuted">暂无缺失记录</div>
                    </div>

                    <div v-else-if="activeTab === 'notifications'" class="space-y-6">
                        <div>
                            <h2 class="text-2xl font-bold">通知配置</h2>
                            <p class="mt-1 text-sm text-textMuted">Telegram 推送设置。</p>
                        </div>
                        <label class="flex items-center gap-3 text-sm font-medium">
                            <input v-model="state.notify.enable_push" type="checkbox">
                            启用 Telegram 推送
                        </label>
                        <input v-model="state.notify.bot_token" class="input-dark" placeholder="Bot Token">
                        <input v-model="state.notify.chat_id" class="input-dark" placeholder="Chat ID，可多个逗号分隔">
                        <input v-model="state.notify.web_base_url" class="input-dark" placeholder="在线地址前缀">
                        <div class="flex flex-wrap gap-3">
                            <button type="button" class="secondary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="testNotify">
                                <AppIcon name="satellite-dish" :size="16" />测试连接
                            </button>
                            <button type="button" class="primary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="saveNotify">
                                <AppIcon name="save" :size="16" />保存通知配置
                            </button>
                        </div>
                    </div>

                    <div v-else-if="activeTab === 'maintenance'" class="space-y-8">
                        <div>
                            <h2 class="text-2xl font-bold">高级工具</h2>
                            <p class="mt-1 text-sm text-textMuted">本地批量导入与 3MF 整理。</p>
                        </div>

                        <div class="rounded-2xl border border-borderSoft bg-panelSoft p-5 space-y-4">
                            <div class="text-lg font-bold">本地批量导入</div>
                            <label class="flex items-center gap-3 text-sm font-medium"><input v-model="state.batch.enabled" type="checkbox">启用监控</label>
                            <textarea v-model="state.batch.watch_dirs" rows="5" class="textarea-dark" placeholder="每行一个目录"></textarea>
                            <div class="grid gap-4 md:grid-cols-2">
                                <input v-model.number="state.batch.scan_interval_seconds" type="number" class="input-dark" placeholder="扫描间隔秒数">
                                <input v-model.number="state.batch.max_parse_workers" type="number" class="input-dark" placeholder="解析并发">
                            </div>
                            <div class="flex flex-wrap gap-3">
                                <button type="button" class="secondary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="runBatch">
                                    <AppIcon name="play" :size="16" />立即扫描
                                </button>
                                <button type="button" class="primary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="saveBatch">
                                    <AppIcon name="save" :size="16" />保存导入配置
                                </button>
                            </div>
                        </div>

                        <div class="rounded-2xl border border-borderSoft bg-panelSoft p-5 space-y-4">
                            <div class="text-lg font-bold">本地 3MF 整理</div>
                            <input v-model="state.organizer.root_dir" class="input-dark" placeholder="整理目录">
                            <select v-model="state.organizer.mode" class="select-dark">
                                <option value="move">移动</option>
                                <option value="copy">复制</option>
                            </select>
                            <div class="flex flex-wrap gap-3">
                                <button type="button" class="secondary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="runOrganizer">
                                    <AppIcon name="play" :size="16" />开始整理
                                </button>
                                <button type="button" class="primary-btn inline-flex items-center gap-2 rounded-2xl px-4 py-3" @click="saveOrganizer">
                                    <AppIcon name="save" :size="16" />保存整理配置
                                </button>
                            </div>
                        </div>
                    </div>
                </section>
                </div>
            </div>
        </div>
    `,
    setup() {
        const loading = ref(true);
        const activeTab = ref('cookies');
        const tabs = [
            { id: 'cookies', label: '配置信息', icon: 'cookie' },
            { id: 'archive', label: '模型归档', icon: 'archive' },
            { id: 'missing', label: '缺失记录', icon: 'alert-circle' },
            { id: 'notifications', label: '通知配置', icon: 'bell' },
            { id: 'maintenance', label: '高级工具', icon: 'wrench' }
        ];
        const state = reactive({
            config: {},
            archiveUrl: '',
            missing: [],
            notify: { enable_push: false, bot_token: '', chat_id: '', web_base_url: '' },
            batch: { enabled: false, watch_dirs: '', scan_interval_seconds: 300, max_parse_workers: 2 },
            organizer: { root_dir: '', mode: 'move' },
            cookieStore: { cn: '', global: '' },
            cookieCounts: { cn: 0, global: 0 }
        });
        const totalCookieCount = computed(() => Number(state.cookieCounts.cn || 0) + Number(state.cookieCounts.global || 0));

        async function loadBundle() {
            loading.value = true;
            const res = await ApiService.getConfigBundle();
            loading.value = false;
            if (res.code !== 0) return;
            const data = res.data;
            state.config = data.config || {};
            state.missing = Array.isArray(data.missing) ? data.missing : [];
            const tg = data.notify && data.notify.telegram ? data.notify.telegram : {};
            state.notify.enable_push = !!tg.enable_push;
            state.notify.bot_token = tg.bot_token || '';
            state.notify.chat_id = tg.chat_id || '';
            state.notify.web_base_url = tg.web_base_url || 'http://127.0.0.1:8000';
            const batchConfig = data.batch && data.batch.config ? data.batch.config : {};
            state.batch.enabled = !!batchConfig.enabled;
            state.batch.watch_dirs = Array.isArray(batchConfig.watch_dirs) ? batchConfig.watch_dirs.join('\n') : '';
            state.batch.scan_interval_seconds = batchConfig.scan_interval_seconds || 300;
            state.batch.max_parse_workers = batchConfig.max_parse_workers || 2;
            const organizerConfig = data.organizer && data.organizer.config ? data.organizer.config : {};
            state.organizer.root_dir = organizerConfig.root_dir || '';
            state.organizer.mode = organizerConfig.mode || 'move';
            const cookieStore = data.cookies && data.cookies.cookie_store ? data.cookies.cookie_store : {};
            state.cookieStore.cn = Array.isArray(cookieStore.cn) ? cookieStore.cn.join('\n') : '';
            state.cookieStore.global = Array.isArray(cookieStore.global) ? cookieStore.global.join('\n') : '';
            const cookieCounts = data.config && data.config.cookie_counts ? data.config.cookie_counts : {};
            state.cookieCounts.cn = Number(cookieCounts.cn || (Array.isArray(cookieStore.cn) ? cookieStore.cn.length : 0));
            state.cookieCounts.global = Number(cookieCounts.global || (Array.isArray(cookieStore.global) ? cookieStore.global.length : 0));
        }

        async function saveCookies() {
            await ApiService.saveCookies({
                cn: state.cookieStore.cn.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
                global: state.cookieStore.global.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
            });
            await loadBundle();
            window.alert('Cookie 已保存');
        }

        async function startArchive() {
            if (!state.archiveUrl.trim()) return;
            const result = await ApiService.archiveModel(state.archiveUrl.trim());
            await loadBundle();
            window.alert(result.message || '归档完成');
        }

        async function retryMissing() {
            const result = await ApiService.retryMissing3mf();
            await loadBundle();
            window.alert(`重新下载完成: 成功 ${result.success || 0}/${result.processed || 0}`);
        }

        async function saveNotify() {
            await ApiService.saveNotifyConfig({ telegram: state.notify });
            await loadBundle();
            window.alert('通知配置已保存');
        }

        async function testNotify() {
            const result = await ApiService.testNotify();
            window.alert(`测试消息已发送: ${result.success_count || 0}/${result.total_chat_ids || 0}`);
        }

        async function saveBatch() {
            await ApiService.saveLocalBatchConfig({
                local_batch_import: {
                    enabled: state.batch.enabled,
                    watch_dirs: state.batch.watch_dirs.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
                    scan_interval_seconds: Number(state.batch.scan_interval_seconds || 300),
                    max_parse_workers: Number(state.batch.max_parse_workers || 2)
                }
            });
            await loadBundle();
            window.alert('批量导入配置已保存');
        }

        async function runBatch() {
            const result = await ApiService.runLocalBatchImport();
            await loadBundle();
            window.alert(`处理 ${result.processed || 0}，新增模型 ${result.created_models || 0}，新增配置 ${result.appended_instances || 0}`);
        }

        async function saveOrganizer() {
            await ApiService.saveLocal3mfOrganizerConfig({ local_3mf_organizer: state.organizer });
            await loadBundle();
            window.alert('整理配置已保存');
        }

        async function runOrganizer() {
            const result = await ApiService.runLocal3mfOrganizer(state.organizer);
            await loadBundle();
            window.alert(`整理完成：扫描 ${result.scanned_files || 0}，模型 ${result.organized_models || 0}，配置 ${result.organized_configs || 0}`);
        }

        onMounted(loadBundle);

        return { loading, activeTab, tabs, state, totalCookieCount, saveCookies, startArchive, retryMissing, saveNotify, testNotify, saveBatch, runBatch, saveOrganizer, runOrganizer };
    }
};

window.AppViews = { HomeView, DetailView, ConfigView };
})();
