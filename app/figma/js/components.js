(() => {
const AppIcon = {
    props: {
        name: { type: String, required: true },
        size: { type: [Number, String], default: 18 },
        stroke: { type: [Number, String], default: 2 }
    },
    template: '<i :data-lucide="name" style="display:inline-flex;"></i>',
    mounted() { this.renderIcon(); },
    updated() { this.renderIcon(); },
    methods: {
        renderIcon() {
            if (!window.lucide) return;
            this.$nextTick(() => {
                const parent = this.$el.parentNode || this.$el;
                lucide.createIcons({ root: parent, attrs: { width: this.size, height: this.size, 'stroke-width': this.stroke } });
            });
        }
    }
};

const AppToast = {
    template: `
        <transition name="toast">
            <div v-if="visible" class="fixed bottom-6 left-1/2 z-[120] -translate-x-1/2">
                <div class="px-4 py-3 rounded-2xl shadow-glow text-sm font-medium"
                    :class="kind === 'error' ? 'bg-red-900 text-red-100 border border-red-700' : 'bg-panelHard text-white border border-cyan/30'">
                    {{ message }}
                </div>
            </div>
        </transition>
    `,
    data() {
        return { visible: false, message: '', kind: 'success', timer: null };
    },
    methods: {
        show(message, kind = 'success', delay = 2200) {
            window.clearTimeout(this.timer);
            this.message = message;
            this.kind = kind;
            this.visible = true;
            this.timer = window.setTimeout(() => {
                this.visible = false;
            }, delay);
        }
    }
};

const LibrarySidebar = {
    components: { AppIcon },
    props: {
        sources: { type: Array, required: true },
        folders: { type: Array, required: true },
        categories: { type: Array, required: true },
        selectedSource: { type: String, default: 'all' },
        selectedFolder: { type: String, default: '' },
        selectedCategory: { type: String, default: '' },
        favoritesOnly: { type: Boolean, default: false },
        printedOnly: { type: Boolean, default: false }
    },
    emits: ['select-source', 'select-folder', 'select-category', 'toggle-favorites', 'toggle-printed'],
    template: `
        <aside class="app-sidebar w-[264px] shrink-0 rounded-[28px] border border-borderSoft bg-panel shadow-card sidebar-scroll overflow-auto">
            <div class="p-5 space-y-7">
                <section>
                    <div class="flex items-center gap-2 text-cyan text-sm font-semibold mb-3">
                        <AppIcon name="globe" :size="16" />
                        来源
                    </div>
                    <div class="space-y-2">
                        <button v-for="source in sources" :key="source.id" type="button"
                            @click="$emit('select-source', source.id)"
                            class="w-full flex items-center justify-between rounded-2xl px-4 py-3 text-left transition"
                            :class="selectedSource === source.id ? 'bg-cyan/20 text-cyan border border-cyan/30' : 'bg-panelSoft text-textMain border border-transparent hover:border-borderStrong'">
                            <span class="font-medium">{{ source.label }}</span>
                            <span class="text-xs text-textMuted">{{ source.count }}</span>
                        </button>
                    </div>
                </section>

                <section>
                    <div class="flex items-center gap-2 text-amber text-sm font-semibold mb-3">
                        <AppIcon name="funnel" :size="16" />
                        筛选
                    </div>
                    <div class="space-y-2">
                        <button type="button" @click="$emit('toggle-favorites')"
                            class="w-full flex items-center gap-3 rounded-2xl px-4 py-3 border transition"
                            :class="favoritesOnly ? 'bg-amber-500/15 text-amber border-amber-500/25' : 'bg-panelSoft text-textMain border-transparent hover:border-borderStrong'">
                            <AppIcon name="heart" :size="16" />
                            <span class="font-medium">只看收藏</span>
                        </button>
                        <button type="button" @click="$emit('toggle-printed')"
                            class="w-full flex items-center gap-3 rounded-2xl px-4 py-3 border transition"
                            :class="printedOnly ? 'bg-green/15 text-green border-green/25' : 'bg-panelSoft text-textMain border-transparent hover:border-borderStrong'">
                            <AppIcon name="badge-check" :size="16" />
                            <span class="font-medium">只看已打印</span>
                        </button>
                    </div>
                </section>

                <section>
                    <div class="flex items-center gap-2 text-violet-400 text-sm font-semibold mb-3">
                        <AppIcon name="folder-heart" :size="16" />
                        收藏夹
                    </div>
                    <div class="space-y-2">
                        <button type="button" @click="$emit('select-folder', '')"
                            class="w-full flex items-center justify-between rounded-2xl px-4 py-3 border transition"
                            :class="!selectedFolder ? 'bg-cyan/20 text-cyan border-cyan/30' : 'bg-panelSoft text-textMain border-transparent hover:border-borderStrong'">
                            <span class="font-medium">全部</span>
                        </button>
                        <button v-for="folder in folders" :key="folder.id" type="button"
                            @click="$emit('select-folder', folder.id)"
                            class="w-full flex items-center justify-between rounded-2xl px-4 py-3 border transition"
                            :class="selectedFolder === folder.id ? 'bg-cyan/20 text-cyan border-cyan/30' : 'bg-panelSoft text-textMain border-transparent hover:border-borderStrong'">
                            <span class="font-medium">{{ folder.name }}</span>
                            <span class="text-xs text-textMuted">{{ folder.modelIds.length }}</span>
                        </button>
                    </div>
                </section>

                <section>
                    <div class="flex items-center gap-2 text-cyan text-sm font-semibold mb-3">
                        <AppIcon name="tags" :size="16" />
                        分类
                    </div>
                    <div class="flex flex-wrap gap-2">
                        <button type="button" class="tag-chip" :class="!selectedCategory ? 'ring-1 ring-cyan/60 text-cyan' : ''"
                            @click="$emit('select-category', '')">全部</button>
                        <button v-for="category in categories" :key="category" type="button" class="tag-chip"
                            :class="selectedCategory === category ? 'ring-1 ring-cyan/60 text-cyan' : ''"
                            @click="$emit('select-category', category)">
                            {{ category }}
                        </button>
                    </div>
                </section>
            </div>
        </aside>
    `
};

const ModelCard = {
    components: { AppIcon },
    props: {
        model: { type: Object, required: true },
        compact: { type: Boolean, default: false },
        batchMode: { type: Boolean, default: false },
        selected: { type: Boolean, default: false }
    },
    emits: ['open', 'toggle-select', 'toggle-favorite'],
    methods: {
        clickCard() {
            if (this.batchMode) this.$emit('toggle-select', this.model.id);
            else this.$emit('open', this.model.id);
        }
    },
    template: `
        <article class="group relative overflow-hidden rounded-[26px] border border-borderSoft bg-panel shadow-card transition duration-200 hover:-translate-y-1 hover:border-cyan/30"
            :class="selected ? 'selection-ring' : ''">
            <button v-if="batchMode" type="button"
                class="absolute left-3 top-3 z-10 h-8 w-8 rounded-xl border border-white/15 backdrop-blur flex items-center justify-center"
                :class="selected ? 'bg-cyan text-white' : 'bg-black/40 text-white/70'"
                @click.stop="$emit('toggle-select', model.id)">
                <AppIcon :name="selected ? 'check' : 'plus'" :size="16" />
            </button>

            <button type="button" class="w-full text-left" @click="clickCard">
                <div class="relative" :class="compact ? 'aspect-square' : 'aspect-[4/3]'">
                    <img :src="model.coverImage" :alt="model.title" class="h-full w-full object-cover transition duration-300 group-hover:scale-105">
                    <div class="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/80 to-transparent"></div>
                    <div class="absolute right-3 top-3 flex flex-col gap-2">
                        <span v-if="model.isFavorited" class="rounded-full bg-amber-400/90 px-2 py-1 text-[11px] font-semibold text-black">收藏</span>
                        <span v-if="model.isPrinted" class="rounded-full bg-green/90 px-2 py-1 text-[11px] font-semibold text-white">已打印</span>
                    </div>
                    <div class="absolute bottom-3 left-3 right-3">
                        <div class="source-chip" :class="model.source === 'localmodel' ? 'secondary' : ''">
                            <AppIcon name="map-pinned" :size="13" />
                            <span>{{ model.sourceLabel }}</span>
                        </div>
                    </div>
                </div>
                <div class="p-4" :class="compact ? 'space-y-3' : 'space-y-4'">
                    <div>
                        <h3 class="line-clamp-2 text-lg font-bold leading-7 text-white">{{ model.title }}</h3>
                        <div class="mt-2 flex items-center gap-2 text-sm text-textMuted">
                            <span class="inline-flex h-7 w-7 items-center justify-center rounded-full bg-cyan/15 text-cyan font-bold">
                                {{ (model.author || '?').slice(0, 1) }}
                            </span>
                            <span>{{ model.author }}</span>
                        </div>
                    </div>

                    <div class="grid grid-cols-4 gap-2 text-sm text-textMuted">
                        <div class="flex items-center gap-1.5"><AppIcon name="thumbs-up" :size="14" />{{ model.likes }}</div>
                        <div class="flex items-center gap-1.5"><AppIcon name="star" :size="14" />{{ model.favorites }}</div>
                        <div class="flex items-center gap-1.5"><AppIcon name="printer" :size="14" />{{ model.prints }}</div>
                        <div class="flex items-center gap-1.5"><AppIcon name="download" :size="14" />{{ model.downloads }}</div>
                    </div>

                    <div class="flex flex-wrap gap-2">
                        <span v-for="tag in model.tags.slice(0, compact ? 2 : 3)" :key="tag" class="tag-chip">{{ tag }}</span>
                    </div>

                    <div class="flex items-center justify-between border-t border-borderSoft pt-3 text-sm text-textMuted">
                        <div class="space-y-1">
                            <div>发布 {{ model.publishDate }}</div>
                            <div>采集 {{ model.archivedDate }}</div>
                        </div>
                        <div class="flex items-center gap-2">
                            <button type="button" class="secondary-btn inline-flex h-9 w-9 items-center justify-center rounded-xl"
                                @click.stop="$emit('toggle-favorite', model.id)">
                                <AppIcon name="heart" :size="16" :class="model.isFavorited ? 'text-amber-400' : 'text-textMuted'" />
                            </button>
                            <button type="button" class="secondary-btn inline-flex h-9 w-9 items-center justify-center rounded-xl"
                                @click.stop="$emit('open', model.id)">
                                <AppIcon name="arrow-up-right" :size="16" />
                            </button>
                        </div>
                    </div>
                </div>
            </button>
        </article>
    `
};

window.AppComponents = { AppIcon, AppToast, LibrarySidebar, ModelCard };
})();
