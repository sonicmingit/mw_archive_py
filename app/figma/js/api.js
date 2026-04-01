(() => {
function sourceLabelOf(source) {
    if (source === 'mw_global') return 'MakerWorld 国际';
    if (source === 'localmodel') return '手动导入';
    if (source === 'others') return '其他来源';
    return 'MakerWorld 国内';
}

function assetUrl(relPath) {
    return new URL(relPath, window.location.href.split('#')[0]).toString();
}

function encodeRelPath(relPath) {
    return String(relPath || '')
        .split('/')
        .filter(Boolean)
        .map((segment) => encodeURIComponent(segment))
        .join('/');
}

function modelFileUrl(modelDir, relPath) {
    return `/api/models/${encodeURIComponent(modelDir)}/file/${encodeRelPath(relPath)}`;
}

function htmlToText(html) {
    const box = document.createElement('div');
    box.innerHTML = String(html || '');
    return (box.textContent || box.innerText || '').trim();
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

function normalizeFlags(raw) {
    const data = raw && typeof raw === 'object' ? raw : {};
    return {
        favorites: Array.isArray(data.favorites) ? data.favorites.map(String) : [],
        printed: Array.isArray(data.printed) ? data.printed.map(String) : [],
        folders: Array.isArray(data.folders) ? data.folders.map((folder) => ({
            id: String(folder.id || ''),
            name: String(folder.name || '').trim(),
            description: String(folder.description || '').trim(),
            modelIds: Array.isArray(folder.modelDirs) ? folder.modelDirs.map(String) : (Array.isArray(folder.modelIds) ? folder.modelIds.map(String) : [])
        })).filter((folder) => folder.id && folder.name) : []
    };
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
    }
    return response.json();
}

async function loadFlags() {
    return normalizeFlags(await fetchJson('/api/gallery/flags'));
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
    await fetchJson('/api/gallery/flags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
}

function mapGalleryItem(item, flags) {
    const stats = item.stats || {};
    return {
        id: String(item.dir || ''),
        dir: String(item.dir || ''),
        title: item.title || item.baseName || '未命名模型',
        author: item.author && item.author.name ? item.author.name : '未知作者',
        coverImage: item.cover ? modelFileUrl(item.dir, `images/${item.cover}`) : assetUrl('./fav.png'),
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
        isFavorited: flags.favorites.includes(String(item.dir || '')),
        isPrinted: flags.printed.includes(String(item.dir || '')),
        collections: flags.folders.filter((folder) => folder.modelIds.includes(String(item.dir || ''))).map((folder) => folder.id),
        images: item.cover ? [modelFileUrl(item.dir, `images/${item.cover}`)] : [assetUrl('./fav.png')],
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

    const cover = meta.cover && meta.cover.relPath ? meta.cover.relPath : '';
    add(cover);
    if (Array.isArray(meta.designImages)) meta.designImages.forEach((item) => add(item.relPath || `images/${item.fileName || ''}`));
    const rawImages = meta.images && typeof meta.images === 'object' ? meta.images : {};
    if (Array.isArray(rawImages.design)) rawImages.design.forEach((name) => add(`images/${name}`));
    if (!images.length) images.push(assetUrl('./fav.png'));
    return images;
}

function deriveMaterials(inst) {
    const out = [];
    const pushMaterial = (type, color, weight) => {
        const key = `${type}|${color}|${weight}`;
        if (!out.find((item) => item.key === key)) out.push({ key, type, color, weight });
    };

    (Array.isArray(inst.instanceFilaments) ? inst.instanceFilaments : []).forEach((item) => {
        pushMaterial(String(item.displayName || item.type || 'PLA'), String(item.color || '#9ca3af'), Number(item.weight || item.usedWeight || 0));
    });
    (Array.isArray(inst.plates) ? inst.plates : []).forEach((plate) => {
        (Array.isArray(plate.filaments) ? plate.filaments : []).forEach((item) => {
            pushMaterial(String(item.type || item.displayName || 'PLA'), String(item.color || '#9ca3af'), Number(item.weight || item.usedWeight || 0));
        });
    });

    return out.map(({ key, ...rest }) => rest);
}

function mapPrintProfiles(meta, modelDir) {
    const instances = Array.isArray(meta.instances) ? meta.instances : [];
    return instances.map((inst) => {
        const pictures = Array.isArray(inst.pictures) ? inst.pictures : [];
        const plates = Array.isArray(inst.plates) ? inst.plates : [];
        const previewImages = pictures.map((item) => modelFileUrl(modelDir, item.relPath || `images/${item.fileName || ''}`));
        const platesDetail = plates.map((plate, index) => ({
            id: String(plate.index || index + 1),
            name: `盘 ${plate.index || index + 1}`,
            time: formatDuration(plate.prediction || inst.prediction || 0),
            weight: `${Number(plate.weight || 0)} g`,
            materialLabel: `${(Array.isArray(plate.filaments) ? plate.filaments.map((item) => item.type || 'PLA').join(' / ') : 'PLA') || 'PLA'} | ${Number(plate.weight || 0)} g`,
            previewImage: plate.thumbnailRelPath ? modelFileUrl(modelDir, plate.thumbnailRelPath) : (previewImages[0] || assetUrl('./fav.png'))
        }));

        return {
            id: Number(inst.id || 0),
            name: inst.title || inst.name || `配置 ${inst.id || ''}`,
            plates: plates.length,
            duration: formatDuration(inst.prediction || 0),
            totalWeight: Number(inst.weight || 0),
            summary: inst.summary || '',
            previewImages: previewImages.length ? previewImages : platesDetail.map((item) => item.previewImage),
            materials: deriveMaterials(inst),
            platesDetail
        };
    });
}

function mapAttachments(meta, modelDir) {
    const names = meta.offlineFiles && Array.isArray(meta.offlineFiles.attachments) ? meta.offlineFiles.attachments : [];
    return names.map((name, index) => ({
        id: `${index}`,
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
        coverImage: meta.cover && meta.cover.relPath ? modelFileUrl(modelDir, meta.cover.relPath) : assetUrl('./fav.png'),
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

window.ApiService = {
    async getLibrary() {
        const [items, flags] = await Promise.all([fetchJson('/api/gallery'), loadFlags()]);
        return {
            code: 0,
            data: {
                models: (Array.isArray(items) ? items : []).map((item) => mapGalleryItem(item, flags)),
                folders: flags.folders
            }
        };
    },

    async getModelDetail(id) {
        const modelDir = decodeURIComponent(String(id || ''));
        const [meta, flags] = await Promise.all([
            fetchJson(`/api/v2/models/${encodeURIComponent(modelDir)}/meta`),
            loadFlags()
        ]);
        return {
            code: 0,
            data: {
                model: mapMetaToModel(meta, modelDir, flags),
                folders: flags.folders
            }
        };
    },

    async toggleFavorite(id) {
        const modelId = String(id || '');
        const flags = await loadFlags();
        const next = new Set(flags.favorites);
        if (next.has(modelId)) next.delete(modelId); else next.add(modelId);
        flags.favorites = [...next];
        await saveFlags(flags);
        return { code: 0 };
    },

    async saveFolder(folderDraft, modelIds) {
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
        return { code: 0, data: flags };
    },

    async updateSourceMark(modelId, payload) {
        await fetchJson(`/api/models/${encodeURIComponent(String(modelId || ''))}/source-meta`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        return { code: 0 };
    },

    async importPrintProfile(modelId, file, title, summary) {
        const form = new FormData();
        form.append('file', file);
        form.append('title', title || '');
        form.append('summary', summary || '');
        await fetchJson(`/api/models/${encodeURIComponent(String(modelId || ''))}/instances/import-3mf`, {
            method: 'POST',
            body: form
        });
        return { code: 0 };
    },

    async getConfigBundle() {
        const [config, notify, batch, organizer, missing, cookies] = await Promise.all([
            fetchJson('/api/config'),
            fetchJson('/api/notify-config'),
            fetchJson('/api/local-batch-import/config'),
            fetchJson('/api/local-3mf-organizer/config'),
            fetchJson('/api/logs/missing-3mf'),
            fetchJson('/api/cookies')
        ]);
        return { code: 0, data: { config, notify, batch, organizer, missing, cookies } };
    },

    async saveCookies(cookieStore) {
        return fetchJson('/api/cookies', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cookie_store: cookieStore })
        });
    },

    async archiveModel(url) {
        return fetchJson('/api/archive', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
    },

    async saveNotifyConfig(payload) {
        return fetchJson('/api/notify-config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    },

    async testNotify() {
        return fetchJson('/api/notify-test', { method: 'POST' });
    },

    async saveLocalBatchConfig(payload) {
        return fetchJson('/api/local-batch-import/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    },

    async runLocalBatchImport() {
        return fetchJson('/api/local-batch-import/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
    },

    async saveLocal3mfOrganizerConfig(payload) {
        return fetchJson('/api/local-3mf-organizer/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    },

    async runLocal3mfOrganizer(payload) {
        return fetchJson('/api/local-3mf-organizer/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    },

    async retryMissing3mf() {
        return fetchJson('/api/logs/missing-3mf/redownload', { method: 'POST' });
    },

    async getMissing3mf() {
        return fetchJson('/api/logs/missing-3mf');
    }
};
})();
