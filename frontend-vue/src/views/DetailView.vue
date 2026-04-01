<script setup>
import { onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ArrowLeft, Bookmark, ExternalLink, FileText, FolderOpen, Globe2, Heart, Layers3, Paperclip, PenLine, Plus, Printer, Save } from 'lucide-vue-next';
import PlateModal from '@/components/PlateModal.vue';
import { getInstanceDownloadUrl, getModelDetail, getSourceOptions, importPrintProfile, toggleFavorite, updateSourceMark } from '@/api/models';

const route = useRoute();
const router = useRouter();

const loading = ref(false);
const model = ref(null);
const activeImage = ref('');
const showSourceEditor = ref(false);
const showAddProfile = ref(false);
const activePlateProfile = ref(null);
const sourceOptions = getSourceOptions().filter((item) => item.id !== 'all');

const sourceForm = reactive({
  source: 'mw_cn',
  sourceUrl: '',
  sourceMark: ''
});

const profileForm = reactive({
  name: '',
  summary: '',
  file: null,
  fileName: ''
});

async function loadDetail() {
  loading.value = true;
  try {
    const data = await getModelDetail(route.params.id);
    model.value = data.model;
    activeImage.value = data.model.images[0] || data.model.coverImage;
    sourceForm.source = data.model.source;
    sourceForm.sourceUrl = data.model.sourceUrl || '';
    sourceForm.sourceMark = data.model.sourceMark || '';
  } finally {
    loading.value = false;
  }
}

async function onToggleFavorite() {
  await toggleFavorite(route.params.id);
  await loadDetail();
}

async function saveSource() {
  await updateSourceMark(route.params.id, sourceForm);
  showSourceEditor.value = false;
  await loadDetail();
}

function handleProfileFileChange(event) {
  const file = event.target.files && event.target.files[0] ? event.target.files[0] : null;
  profileForm.file = file;
  profileForm.fileName = file ? file.name : '';
}

async function saveProfile() {
  if (!profileForm.file) return;
  await importPrintProfile(route.params.id, profileForm.file, profileForm.name, profileForm.summary);
  profileForm.name = '';
  profileForm.summary = '';
  profileForm.file = null;
  profileForm.fileName = '';
  showAddProfile.value = false;
  await loadDetail();
}

function openProfileDetail(profile) {
  activePlateProfile.value = profile;
}

function printProfile(profile) {
  window.open(getInstanceDownloadUrl(route.params.id, profile.id), '_blank');
}

function previewProfile(profile) {
  if (profile.previewImages.length) activeImage.value = profile.previewImages[0];
}

function downloadAttachment(attachment) {
  if (attachment.url) window.open(attachment.url, '_blank');
}

watch(() => route.params.id, () => route.params.id && loadDetail());

onMounted(loadDetail);
</script>

<template>
  <section class="detail-page">
    <button class="btn btn-link" type="button" @click="router.push({ name: 'home' })">
      <ArrowLeft :size="16" />
      返回模型库
    </button>

    <div v-if="loading" class="panel empty-state">
      <div class="spinner" />
    </div>
    <div v-else-if="model" class="detail-layout">
      <div class="detail-main">
        <div class="panel detail-gallery">
          <div class="hero-image">
            <img :src="activeImage" :alt="model.title" />
          </div>
          <div class="thumb-row">
            <button v-for="image in model.images" :key="image" class="thumb-button" :class="{ active: activeImage === image }" type="button" @click="activeImage = image">
              <img :src="image" alt="" />
            </button>
          </div>
        </div>

        <div class="panel">
          <div class="section-heading"><FileText :size="16" />模型简介</div>
          <div class="rich-text" v-html="model.description" />
        </div>

        <div class="panel form-stack">
          <div class="section-row">
            <div class="section-heading"><Layers3 :size="16" />打印配置</div>
            <button class="btn btn-primary" type="button" @click="showAddProfile = true">
              <Plus :size="16" />
              添加打印配置
            </button>
          </div>

          <div v-if="model.printProfiles.length" class="profile-list">
            <article v-for="profile in model.printProfiles" :key="profile.id" class="profile-card">
              <div class="profile-header">
                <div>
                  <h3>{{ profile.name }}</h3>
                  <p>{{ profile.summary || '暂无说明' }}</p>
                </div>
                <div class="toolbar">
                  <button class="btn btn-danger" type="button" @click="openProfileDetail(profile)">详情</button>
                  <button class="btn btn-primary" type="button" @click="printProfile(profile)">
                    <Printer :size="16" />
                    打印
                  </button>
                  <button class="btn btn-success" type="button" @click="previewProfile(profile)">预览</button>
                </div>
              </div>

              <div class="chip-list">
                <span class="chip chip-static">{{ profile.plates }} 盘</span>
                <span class="chip chip-static">{{ profile.duration }}</span>
                <span class="chip chip-static">{{ profile.totalWeight }} g</span>
              </div>

              <div class="chip-list">
                <span v-for="material in profile.materials" :key="`${material.type}-${material.color}`" class="chip chip-static">
                  {{ material.type }} {{ material.weight }} g
                </span>
              </div>

              <div v-if="profile.previewImages.length" class="preview-row">
                <img v-for="image in profile.previewImages" :key="image" :src="image" alt="" />
              </div>
            </article>
          </div>
          <div v-else class="empty-inline">当前还没有打印配置，点击右上角按钮新增。</div>
        </div>
      </div>

      <aside class="detail-side">
        <div class="panel">
          <div class="section-row">
            <div>
              <h1 class="detail-title">{{ model.title }}</h1>
              <p class="detail-author">{{ model.author }}</p>
            </div>
            <button class="btn btn-secondary btn-icon" type="button" @click="onToggleFavorite">
              <Heart :size="18" :class="{ 'icon-active': model.isFavorited }" />
            </button>
          </div>

          <div class="pill-row">
            <span class="pill"><Globe2 :size="14" />{{ model.sourceLabel }}</span>
            <span class="pill pill-muted"><Bookmark :size="14" />{{ model.sourceMark || '未标记' }}</span>
            <a v-if="model.sourceUrl" class="pill pill-muted" :href="model.sourceUrl" target="_blank" rel="noreferrer">
              <ExternalLink :size="14" />
              来源链接
            </a>
          </div>

          <div class="stat-grid">
            <div class="stat-box"><span>点赞</span><strong>{{ model.likes }}</strong></div>
            <div class="stat-box"><span>收藏</span><strong>{{ model.favorites }}</strong></div>
            <div class="stat-box"><span>打印</span><strong>{{ model.prints }}</strong></div>
            <div class="stat-box"><span>下载</span><strong>{{ model.downloads }}</strong></div>
          </div>
        </div>

        <div class="panel form-stack">
          <div class="section-row">
            <div class="section-heading"><PenLine :size="16" />来源标记</div>
            <button class="btn btn-secondary" type="button" @click="showSourceEditor = true">编辑</button>
          </div>
          <div class="info-card"><span>来源类型</span><strong>{{ model.sourceLabel }}</strong></div>
          <div class="info-card"><span>标记说明</span><strong>{{ model.sourceMark || '暂无' }}</strong></div>
        </div>

        <div class="panel">
          <div class="section-heading"><FolderOpen :size="16" />标签</div>
          <div class="chip-list">
            <span v-for="tag in model.tags" :key="tag" class="chip chip-static">{{ tag }}</span>
          </div>
        </div>

        <div class="panel">
          <div class="section-heading"><Paperclip :size="16" />附件文件</div>
          <div v-if="model.attachments.length" class="stack-list">
            <div v-for="attachment in model.attachments" :key="attachment.id" class="attach-row">
              <div>
                <strong>{{ attachment.name }}</strong>
                <span>{{ attachment.type }} · {{ attachment.size }}</span>
              </div>
              <button class="btn btn-secondary" type="button" @click="downloadAttachment(attachment)">下载</button>
            </div>
          </div>
          <div v-else class="empty-inline">暂无附件</div>
        </div>
      </aside>
    </div>

    <div v-if="showSourceEditor" class="modal-backdrop" @click.self="showSourceEditor = false">
      <div class="modal panel modal-medium">
        <div class="modal-header">
          <div>
            <h3>编辑来源标记</h3>
            <p>更新来源类型、链接和说明。</p>
          </div>
          <button class="btn btn-secondary btn-icon" type="button" @click="showSourceEditor = false">×</button>
        </div>

        <div class="form-stack">
          <select v-model="sourceForm.source" class="field">
            <option v-for="item in sourceOptions" :key="item.id" :value="item.id">{{ item.label }}</option>
          </select>
          <input v-model="sourceForm.sourceUrl" class="field" type="url" placeholder="来源链接" />
          <textarea v-model="sourceForm.sourceMark" class="field field-textarea" rows="5" placeholder="来源标记说明" />
          <button class="btn btn-primary" type="button" @click="saveSource">
            <Save :size="16" />
            保存来源标记
          </button>
        </div>
      </div>
    </div>

    <div v-if="showAddProfile" class="modal-backdrop" @click.self="showAddProfile = false">
      <div class="modal panel modal-medium">
        <div class="modal-header">
          <div>
            <h3>添加打印配置</h3>
            <p>上传 3MF 文件并保存到当前模型。</p>
          </div>
          <button class="btn btn-secondary btn-icon" type="button" @click="showAddProfile = false">×</button>
        </div>

        <div class="form-stack">
          <input class="field" type="file" accept=".3mf" @change="handleProfileFileChange" />
          <input v-model="profileForm.name" class="field" type="text" placeholder="配置标题，可选" />
          <div class="info-card"><span>当前文件</span><strong>{{ profileForm.fileName || '未选择 3MF 文件' }}</strong></div>
          <textarea v-model="profileForm.summary" class="field field-textarea" rows="4" placeholder="配置说明，可选" />
          <button class="btn btn-primary" type="button" :disabled="!profileForm.file" @click="saveProfile">
            <Plus :size="16" />
            保存配置
          </button>
        </div>
      </div>
    </div>

    <PlateModal :profile="activePlateProfile" @close="activePlateProfile = null" />
  </section>
</template>
