<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { AlertCircle, Archive, ArrowLeft, Bell, Cookie, Play, Save, SatelliteDish, Wrench } from 'lucide-vue-next';
import { useRouter } from 'vue-router';
import {
  archiveModel,
  getConfigBundle,
  retryMissing3mf,
  runLocal3mfOrganizer,
  runLocalBatchImport,
  saveCookies,
  saveLocal3mfOrganizerConfig,
  saveLocalBatchConfig,
  saveNotifyConfig,
  testNotify
} from '@/api/models';

const router = useRouter();
const loading = ref(false);
const activeTab = ref('cookies');

const tabs = [
  { id: 'cookies', label: '配置信息', icon: Cookie },
  { id: 'archive', label: '模型归档', icon: Archive },
  { id: 'missing', label: '缺失记录', icon: AlertCircle },
  { id: 'notifications', label: '通知配置', icon: Bell },
  { id: 'maintenance', label: '高级工具', icon: Wrench }
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
  try {
    const data = await getConfigBundle();
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
  } finally {
    loading.value = false;
  }
}

async function saveCookieStore() {
  await saveCookies({
    cn: state.cookieStore.cn.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
    global: state.cookieStore.global.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
  });
  await loadBundle();
  window.alert('Cookie 已保存');
}

async function startArchive() {
  if (!state.archiveUrl.trim()) return;
  const result = await archiveModel(state.archiveUrl.trim());
  await loadBundle();
  window.alert(result.message || '归档完成');
}

async function redownloadMissing() {
  const result = await retryMissing3mf();
  await loadBundle();
  window.alert(`重新下载完成: 成功 ${result.success || 0}/${result.processed || 0}`);
}

async function saveNotify() {
  await saveNotifyConfig({ telegram: state.notify });
  await loadBundle();
  window.alert('通知配置已保存');
}

async function runNotifyTest() {
  const result = await testNotify();
  window.alert(`测试消息已发送: ${result.success_count || 0}/${result.total_chat_ids || 0}`);
}

async function saveBatch() {
  await saveLocalBatchConfig({
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
  const result = await runLocalBatchImport();
  await loadBundle();
  window.alert(`处理 ${result.processed || 0}，新增模型 ${result.created_models || 0}，新增配置 ${result.appended_instances || 0}`);
}

async function saveOrganizer() {
  await saveLocal3mfOrganizerConfig({ local_3mf_organizer: state.organizer });
  await loadBundle();
  window.alert('整理配置已保存');
}

async function runOrganizer() {
  const result = await runLocal3mfOrganizer(state.organizer);
  await loadBundle();
  window.alert(`整理完成：扫描 ${result.scanned_files || 0}，模型 ${result.organized_models || 0}，配置 ${result.organized_configs || 0}`);
}

onMounted(loadBundle);
</script>

<template>
  <section class="config-page">
    <div class="panel hero-panel">
      <button class="btn btn-link" type="button" @click="router.push({ name: 'home' })">
        <ArrowLeft :size="16" />
        返回模型库
      </button>

      <div class="config-hero">
        <div>
          <h1>控制台</h1>
          <p>独立 Vue 3 前端的系统设置与高级工具。</p>
        </div>
        <div class="toolbar">
          <div class="stat-box">
            <span>Cookie 组数</span>
            <strong>{{ totalCookieCount }}</strong>
          </div>
          <div class="stat-box stat-wide">
            <span>最近更新时间</span>
            <strong>{{ state.config.cookie_updated_at || '暂无' }}</strong>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="panel empty-state">
      <div class="spinner" />
    </div>
    <div v-else class="config-layout">
      <aside class="panel sidebar config-sidebar">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="side-item"
          :class="{ active: activeTab === tab.id }"
          type="button"
          @click="activeTab = tab.id"
        >
          <component :is="tab.icon" :size="16" />
          <span>{{ tab.label }}</span>
        </button>
      </aside>

      <section class="panel config-main">
        <div v-if="activeTab === 'cookies'" class="form-stack">
          <div>
            <h2>Cookie 配置</h2>
            <p>基础路径、Cookie 数量与原始内容编辑。</p>
          </div>

          <div class="stat-grid">
            <div class="stat-box"><span>下载目录</span><strong>{{ state.config.download_dir }}</strong></div>
            <div class="stat-box"><span>日志目录</span><strong>{{ state.config.logs_dir }}</strong></div>
            <div class="stat-box"><span>Cookie 文件</span><strong>{{ state.config.cookie_file }}</strong></div>
          </div>

          <div class="split-panels">
            <div class="panel section-soft form-stack">
              <h3>MakerWorld 国内</h3>
              <p>当前已保存 {{ state.cookieCounts.cn }} 条 Cookie</p>
              <textarea v-model="state.cookieStore.cn" class="field field-textarea" rows="10" placeholder="每行一个 Cookie" />
            </div>
            <div class="panel section-soft form-stack">
              <h3>MakerWorld 国际</h3>
              <p>当前已保存 {{ state.cookieCounts.global }} 条 Cookie</p>
              <textarea v-model="state.cookieStore.global" class="field field-textarea" rows="10" placeholder="每行一个 Cookie" />
            </div>
          </div>

          <button class="btn btn-primary" type="button" @click="saveCookieStore">
            <Save :size="16" />
            保存 Cookie
          </button>
        </div>

        <div v-else-if="activeTab === 'archive'" class="form-stack">
          <div>
            <h2>模型归档</h2>
            <p>输入 MakerWorld 链接并直接调用后端归档。</p>
          </div>
          <input v-model="state.archiveUrl" class="field" type="url" placeholder="https://makerworld.com.cn/..." />
          <button class="btn btn-primary" type="button" @click="startArchive">
            <Archive :size="16" />
            开始归档
          </button>
        </div>

        <div v-else-if="activeTab === 'missing'" class="form-stack">
          <div class="section-row">
            <div>
              <h2>缺失记录</h2>
              <p>重试下载缺失的 3MF 文件。</p>
            </div>
            <button class="btn btn-secondary" type="button" @click="redownloadMissing">
              <AlertCircle :size="16" />
              重新下载
            </button>
          </div>

          <div v-if="state.missing.length" class="stack-list">
            <div v-for="item in state.missing" :key="`${item.time}-${item.base_name}-${item.inst_id}`" class="attach-row">
              <div>
                <strong>{{ item.base_name }}</strong>
                <span>实例 {{ item.inst_id }} · {{ item.title || '未命名配置' }}</span>
              </div>
              <span>{{ item.time }} · {{ item.status }}</span>
            </div>
          </div>
          <div v-else class="empty-inline">暂无缺失记录</div>
        </div>

        <div v-else-if="activeTab === 'notifications'" class="form-stack">
          <div>
            <h2>通知配置</h2>
            <p>Telegram 推送设置。</p>
          </div>
          <label class="toggle-line">
            <input v-model="state.notify.enable_push" type="checkbox" />
            启用 Telegram 推送
          </label>
          <input v-model="state.notify.bot_token" class="field" type="text" placeholder="Bot Token" />
          <input v-model="state.notify.chat_id" class="field" type="text" placeholder="Chat ID，可多个逗号分隔" />
          <input v-model="state.notify.web_base_url" class="field" type="url" placeholder="在线地址前缀" />
          <div class="toolbar">
            <button class="btn btn-secondary" type="button" @click="runNotifyTest">
              <SatelliteDish :size="16" />
              测试连接
            </button>
            <button class="btn btn-primary" type="button" @click="saveNotify">
              <Save :size="16" />
              保存通知配置
            </button>
          </div>
        </div>

        <div v-else class="form-stack">
          <div>
            <h2>高级工具</h2>
            <p>本地批量导入与 3MF 整理。</p>
          </div>

          <div class="panel section-soft form-stack">
            <h3>本地批量导入</h3>
            <label class="toggle-line">
              <input v-model="state.batch.enabled" type="checkbox" />
              启用监控
            </label>
            <textarea v-model="state.batch.watch_dirs" class="field field-textarea" rows="5" placeholder="每行一个目录" />
            <div class="grid-2">
              <input v-model.number="state.batch.scan_interval_seconds" class="field" type="number" placeholder="扫描间隔秒数" />
              <input v-model.number="state.batch.max_parse_workers" class="field" type="number" placeholder="解析并发" />
            </div>
            <div class="toolbar">
              <button class="btn btn-secondary" type="button" @click="runBatch">
                <Play :size="16" />
                立即扫描
              </button>
              <button class="btn btn-primary" type="button" @click="saveBatch">
                <Save :size="16" />
                保存导入配置
              </button>
            </div>
          </div>

          <div class="panel section-soft form-stack">
            <h3>本地 3MF 整理</h3>
            <input v-model="state.organizer.root_dir" class="field" type="text" placeholder="整理目录" />
            <select v-model="state.organizer.mode" class="field">
              <option value="move">移动</option>
              <option value="copy">复制</option>
            </select>
            <div class="toolbar">
              <button class="btn btn-secondary" type="button" @click="runOrganizer">
                <Play :size="16" />
                开始整理
              </button>
              <button class="btn btn-primary" type="button" @click="saveOrganizer">
                <Save :size="16" />
                保存整理配置
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </section>
</template>
