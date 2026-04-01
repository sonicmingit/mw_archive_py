import { buildApiUrl, fetchJson, instanceDownloadUrl, modelFileUrl } from './client';

export function sourceLabelOf(source) {
  if (source === 'mw_global') return 'MakerWorld 国际';
  if (source === 'localmodel') return '手动导入';
  if (source === 'others') return '其他来源';
  return 'MakerWorld 国内';
}

export function getSourceOptions() {
  return [
    { id: 'all', label: '全部' },
    { id: 'mw_cn', label: 'MakerWorld 国内' },
    { id: 'mw_global', label: 'MakerWorld 国际' },
    { id: 'localmodel', label: '手动导入' },
    { id: 'others', label: '其他来源' }
  ];
}

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString('zh-CN');
}

function formatDuration(seconds) {
  const sec = Number(seconds || 0);
  if (!Number.isFinite(sec) || sec <= 0) return '0 min';
  const hours = sec / 3600;
  if (hours >= 1) return `${hours.toFixed(1)} h`;
  return `${(sec / 60).toFixed(1)} min`;
}

function htmlToText(html) {
  const box = document.createElement('div');
  box.innerHTML = String(html || '');
  return (box.textContent || box.innerText || '').trim();
}

function normalizeFlags(raw) {
  const data = raw && typeof raw === 'object' ? raw : {};
  return {
    favorites: Array.isArray(data.favorites) ? data.favorites.map(String) : [],
    printed: Array.isArray(data.printed) ? data.printed.map(String) : [],
    folders: Array.isArray(data.folders)
      ? data.folders
          .map((folder) => ({
            id: String(folder.id || ''),
            name: String(folder.name || '').trim(),
            description: String(folder.description || '').trim(),
            modelIds: Array.isArray(folder.modelDirs)
              ? folder.modelDirs.map(String)
              : Array.isArray(folder.modelIds)
                ? folder.modelIds.map(String)
                : []
          }))
          .filter((folder) => folder.id && folder.name)
      : []
  };
}

async function loadFlags() {
  return normalizeFlags(await fetchJson('/gallery/flags'));
}

async function saveFlags(flags) {
  const payload = {
    favorites: flags.favorites,
    printed: flags.printed,
    folders: flags.folders.map((folder) => ({
      id: folder.id,
      name: folder.name,
      description: folder.description || '',
      modelDirs: folder.modelIds
    }))
  };
  await fetchJson('/gallery/flags', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

function mapGalleryItem(item, flags) {
  const stats = item.stats || {};
  const modelDir = String(item.dir || '');
  const coverImage = item.cover ? modelFileUrl(modelDir, `images/${item.cover}`) : '/fav.png';

  return {
    id: modelDir,
    dir: modelDir,
    title: item.title || item.baseName || '未命名模型',
    author: item.author && item.author.name ? item.author.name : '未知作者',
    coverImage,
    category: '',
    tags: Array.isArray(item.tags) ? item.tags : [],
    description: item.summary || '',
    likes: Number(stats.likes || 0),
    favorites: Number(stats.favorites || 0),
    prints: Number(stats.prints || 0),
    downloads: Number(stats.downloads || 0),
    views: Number(stats.views || 0),
    publishDate: formatDate(item.publishedAt),
    archivedDate: formatDate(item.collectedAt),
    source: String(item.source || 'mw_cn'),
    sourceLabel: sourceLabelOf(item.source),
    sourceMark: '',
    sourceUrl: '',
    isFavorited: flags.favorites.includes(modelDir),
    isPrinted: flags.printed.includes(modelDir),
    collections: flags.folders.filter((folder) => folder.modelIds.includes(modelDir)).map((folder) => folder.id),
    images: [coverImage],
    attachments: [],
    printProfiles: []
  };
}

function extractImages(meta, modelDir) {
  const images = [];
  const add = (relPath) => {
    const clean = String(relPath || '').trim();
    if (!clean) return;
    const full = modelFileUrl(modelDir, clean);
    if (!images.includes(full)) images.push(full);
  };

  add(meta.cover && meta.cover.relPath ? meta.cover.relPath : '');
  if (Array.isArray(meta.designImages)) meta.designImages.forEach((item) => add(item.relPath || `images/${item.fileName || ''}`));
  if (meta.images && Array.isArray(meta.images.design)) meta.images.design.forEach((name) => add(`images/${name}`));
  if (!images.length) images.push('/fav.png');
  return images;
}

function deriveMaterials(instance) {
  const out = [];
  const pushMaterial = (type, color, weight) => {
    const key = `${type}|${color}|${weight}`;
    if (!out.find((item) => item.key === key)) out.push({ key, type, color, weight });
  };

  (Array.isArray(instance.instanceFilaments) ? instance.instanceFilaments : []).forEach((item) => {
    pushMaterial(String(item.displayName || item.type || 'PLA'), String(item.color || '#9ca3af'), Number(item.weight || item.usedWeight || 0));
  });

  (Array.isArray(instance.plates) ? instance.plates : []).forEach((plate) => {
    (Array.isArray(plate.filaments) ? plate.filaments : []).forEach((item) => {
      pushMaterial(String(item.type || item.displayName || 'PLA'), String(item.color || '#9ca3af'), Number(item.weight || item.usedWeight || 0));
    });
  });

  return out.map(({ key, ...rest }) => rest);
}

function mapPrintProfiles(meta, modelDir) {
  const instances = Array.isArray(meta.instances) ? meta.instances : [];
  return instances.map((instance) => {
    const pictures = Array.isArray(instance.pictures) ? instance.pictures : [];
    const plates = Array.isArray(instance.plates) ? instance.plates : [];
    const previewImages = pictures.map((item) => modelFileUrl(modelDir, item.relPath || `images/${item.fileName || ''}`));
    const platesDetail = plates.map((plate, index) => ({
      id: String(plate.index || index + 1),
      name: `盘 ${plate.index || index + 1}`,
      time: formatDuration(plate.prediction || instance.prediction || 0),
      weight: `${Number(plate.weight || 0)} g`,
      materialLabel: `${(Array.isArray(plate.filaments) ? plate.filaments.map((item) => item.type || 'PLA').join(' / ') : 'PLA') || 'PLA'} | ${Number(plate.weight || 0)} g`,
      previewImage: plate.thumbnailRelPath ? modelFileUrl(modelDir, plate.thumbnailRelPath) : (previewImages[0] || '/fav.png')
    }));

    return {
      id: Number(instance.id || 0),
      name: instance.title || instance.name || `配置 ${instance.id || ''}`,
      plates: plates.length,
      duration: formatDuration(instance.prediction || 0),
      totalWeight: Number(instance.weight || 0),
      summary: instance.summary || '',
      previewImages: previewImages.length ? previewImages : platesDetail.map((item) => item.previewImage),
      materials: deriveMaterials(instance),
      platesDetail
    };
  });
}

function mapAttachments(meta, modelDir) {
  const names = meta.offlineFiles && Array.isArray(meta.offlineFiles.attachments) ? meta.offlineFiles.attachments : [];
  return names.map((name, index) => ({
    id: String(index),
    name,
    type: String(name).split('.').pop()?.toUpperCase() || 'FILE',
    size: '--',
    url: modelFileUrl(modelDir, `file/${name}`)
  }));
}

function mapMetaToModel(meta, modelDir, flags) {
  const stats = meta.stats || {};
  const publishedAt = Array.isArray(meta.instances) && meta.instances.length
    ? meta.instances.map((item) => item.publishTime).filter(Boolean).sort()[0]
    : '';

  return {
    id: modelDir,
    dir: modelDir,
    title: meta.title || meta.baseName || modelDir,
    author: meta.author && meta.author.name ? meta.author.name : '未知作者',
    coverImage: meta.cover && meta.cover.relPath ? modelFileUrl(modelDir, meta.cover.relPath) : '/fav.png',
    images: extractImages(meta, modelDir),
    category: String(meta.category || '').trim(),
    tags: Array.isArray(meta.tags) ? meta.tags : [],
    description: meta.summary && meta.summary.html ? meta.summary.html : (meta.summary && meta.summary.text ? meta.summary.text : ''),
    descriptionText: meta.summary && meta.summary.text ? meta.summary.text : htmlToText(meta.summary && meta.summary.html ? meta.summary.html : ''),
    likes: Number(stats.likes || 0),
    favorites: Number(stats.favorites || 0),
    prints: Number(stats.prints || 0),
    downloads: Number(stats.downloads || 0),
    views: Number(stats.views || 0),
    publishDate: formatDate(publishedAt),
    archivedDate: formatDate(meta.collectDate ? new Date(Number(meta.collectDate) * 1000).toISOString() : meta.update_time),
    source: String(meta.source || 'mw_cn'),
    sourceLabel: sourceLabelOf(meta.source),
    sourceMark: String(meta.sourceMark || ''),
    sourceUrl: String(meta.url || meta.sourceLink || ''),
    isFavorited: flags.favorites.includes(modelDir),
    isPrinted: flags.printed.includes(modelDir),
    collections: flags.folders.filter((folder) => folder.modelIds.includes(modelDir)).map((folder) => folder.id),
    attachments: mapAttachments(meta, modelDir),
    printProfiles: mapPrintProfiles(meta, modelDir)
  };
}

export async function getLibrary() {
  const [items, flags] = await Promise.all([fetchJson('/gallery'), loadFlags()]);
  return {
    models: (Array.isArray(items) ? items : []).map((item) => mapGalleryItem(item, flags)),
    folders: flags.folders
  };
}

export async function getModelDetail(modelId) {
  const modelDir = decodeURIComponent(String(modelId || ''));
  const [meta, flags] = await Promise.all([
    fetchJson(`/v2/models/${encodeURIComponent(modelDir)}/meta`),
    loadFlags()
  ]);
  return {
    model: mapMetaToModel(meta, modelDir, flags),
    folders: flags.folders
  };
}

export async function toggleFavorite(modelId) {
  const flags = await loadFlags();
  const next = new Set(flags.favorites);
  if (next.has(modelId)) next.delete(modelId);
  else next.add(modelId);
  flags.favorites = [...next];
  await saveFlags(flags);
}

export async function saveFolder(folderDraft, modelIds) {
  const flags = await loadFlags();
  const folderId = folderDraft.id || `folder_${Date.now()}`;
  let folder = flags.folders.find((item) => item.id === folderId);

  if (!folder) {
    folder = { id: folderId, name: String(folderDraft.name || '').trim(), description: String(folderDraft.description || '').trim(), modelIds: [] };
    flags.folders.push(folder);
  } else {
    folder.name = String(folderDraft.name || folder.name || '').trim();
    folder.description = String(folderDraft.description || '').trim();
  }

  modelIds.map(String).forEach((id) => {
    if (!folder.modelIds.includes(id)) folder.modelIds.push(id);
    if (!flags.favorites.includes(id)) flags.favorites.push(id);
  });

  await saveFlags(flags);
  return flags;
}

export async function updateSourceMark(modelId, payload) {
  return fetchJson(`/models/${encodeURIComponent(String(modelId || ''))}/source-meta`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export async function importPrintProfile(modelId, file, title, summary) {
  const form = new FormData();
  form.append('file', file);
  form.append('title', title || '');
  form.append('summary', summary || '');
  return fetchJson(`/models/${encodeURIComponent(String(modelId || ''))}/instances/import-3mf`, {
    method: 'POST',
    body: form
  });
}

export async function getConfigBundle() {
  const [config, notify, batch, organizer, missing, cookies] = await Promise.all([
    fetchJson('/config'),
    fetchJson('/notify-config'),
    fetchJson('/local-batch-import/config'),
    fetchJson('/local-3mf-organizer/config'),
    fetchJson('/logs/missing-3mf'),
    fetchJson('/cookies')
  ]);
  return { config, notify, batch, organizer, missing, cookies };
}

export async function saveCookies(cookieStore) {
  return fetchJson('/cookies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cookie_store: cookieStore })
  });
}

export async function archiveModel(url) {
  return fetchJson('/archive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url })
  });
}

export async function saveNotifyConfig(payload) {
  return fetchJson('/notify-config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export async function testNotify() {
  return fetchJson('/notify-test', { method: 'POST' });
}

export async function saveLocalBatchConfig(payload) {
  return fetchJson('/local-batch-import/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export async function runLocalBatchImport() {
  return fetchJson('/local-batch-import/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  });
}

export async function saveLocal3mfOrganizerConfig(payload) {
  return fetchJson('/local-3mf-organizer/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export async function runLocal3mfOrganizer(payload) {
  return fetchJson('/local-3mf-organizer/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export async function retryMissing3mf() {
  return fetchJson('/logs/missing-3mf/redownload', { method: 'POST' });
}

export function getInstanceDownloadUrl(modelId, instanceId) {
  return instanceDownloadUrl(modelId, instanceId);
}

export function getApiAbsoluteUrl(path) {
  return buildApiUrl(path);
}
