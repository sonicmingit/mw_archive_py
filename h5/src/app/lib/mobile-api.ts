import { fetchJson, resolveApiUrl, resolveAssetUrl, setApiBaseUrl } from "./api";
import type {
  CookieStoreResponse,
  GalleryFlags,
  MobileArchiveCenterResponse,
  MobileArchiveCreateResponse,
  MobileLibraryItem,
  MobileLibraryResponse,
  MobileModelDetail,
  MobileOverviewResponse,
  MobileSettingsResponse,
  MobileToolsResponse,
  OrganizerRunResponse,
  ScanImportRunResponse,
} from "../types/mobile";

function normalizeLibraryItem(item: MobileLibraryItem): MobileLibraryItem {
  return {
    ...item,
    coverImage: resolveAssetUrl(item.coverImage),
  };
}

function normalizeRichHtml(html?: string) {
  const raw = (html || '').trim();
  if (!raw) {
    return '';
  }

  return raw.replace(
    /\b(src|href|poster)=["']([^"']+)["']/gi,
    (_match, attr: string, value: string) => {
      const resolved = resolveAssetUrl(value);
      return `${attr}="${resolved || value}"`;
    },
  ).replace(
    /url\((['"]?)(\/[^)'"]+)\1\)/gi,
    (_match, quote: string, value: string) => {
      const resolved = resolveApiUrl(value);
      return `url(${quote}${resolved}${quote})`;
    },
  );
}

function normalizeModelDetail(model: MobileModelDetail): MobileModelDetail {
  return {
    ...model,
    coverImage: resolveAssetUrl(model.coverImage),
    images: (model.images || []).map((image) => resolveAssetUrl(image)),
    descriptionHtml: normalizeRichHtml(model.descriptionHtml),
    attachments: (model.attachments || []).map((attachment) => ({
      ...attachment,
      url: resolveAssetUrl(attachment.url),
      previewUrl: resolveAssetUrl(attachment.previewUrl),
      downloadUrl: resolveAssetUrl(attachment.downloadUrl),
    })),
    instances: (model.instances || []).map((instance) => ({
      ...instance,
      image: resolveAssetUrl(instance.image),
      downloadUrl: resolveAssetUrl(instance.downloadUrl),
      plates: (instance.plates || []).map((plate) => ({
        ...plate,
        image: resolveAssetUrl(plate.image),
      })),
    })),
  };
}

export async function getOverview() {
  const data = await fetchJson<MobileOverviewResponse>('/api/mobile/overview');
  return {
    ...data,
    recentModels: (data.recentModels || []).map(normalizeLibraryItem),
  };
}

export async function getLibrary(options?: { refresh?: boolean }) {
  const query = options?.refresh ? '?refresh=1' : '';
  const data = await fetchJson<MobileLibraryResponse>(`/api/mobile/library${query}`);
  return {
    items: (data.items || []).map(normalizeLibraryItem),
  };
}

export async function getGalleryFlags() {
  return fetchJson<GalleryFlags>('/api/gallery/flags');
}

export async function saveGalleryFlags(payload: GalleryFlags) {
  return fetchJson<{ status: string }>('/api/gallery/flags', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getArchiveCenter() {
  return fetchJson<MobileArchiveCenterResponse>('/api/mobile/archive-center');
}

export async function createArchiveTask(url: string) {
  return fetchJson<MobileArchiveCreateResponse>('/api/archive', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export async function redownloadMissingFiles() {
  return fetchJson<{ status: string; success_count?: number; failed_count?: number; message?: string }>(
    '/api/logs/missing-3mf/redownload',
    {
      method: 'POST',
    },
  );
}

export async function getModelDetail(modelId: string) {
  const data = await fetchJson<MobileModelDetail>(`/api/mobile/models/${encodeURIComponent(modelId)}`);
  return normalizeModelDetail(data);
}

export async function getSettings() {
  return fetchJson<MobileSettingsResponse>('/api/mobile/settings');
}

export async function getTools() {
  return fetchJson<MobileToolsResponse>('/api/mobile/tools');
}

export async function saveNotifyConfig(payload: {
  web_base_url: string;
  telegram: {
    enable_push: boolean;
    bot_token: string;
    chat_id: string;
  };
  feishu: {
    enable_push: boolean;
    webhook_url: string;
  };
}) {
  return fetchJson('/api/notify-config', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function testConnection(baseUrl: string) {
  const normalized = trimBaseForTest(baseUrl);
  const response = await fetch(`${normalized}/api/mobile/settings`);
  if (!response.ok) {
    throw new Error(`连接失败 (${response.status})`);
  }
  setApiBaseUrl(normalized);
  return true;
}

function trimBaseForTest(baseUrl: string) {
  return (baseUrl || '').replace(/\/+$/, '');
}

export async function getCookies() {
  return fetchJson<CookieStoreResponse>('/api/cookies');
}

export async function saveCookie(platform: 'cn' | 'global', cookie: string) {
  return fetchJson('/api/cookie', {
    method: 'POST',
    body: JSON.stringify({
      platform,
      cookie,
      append: false,
    }),
  });
}

export async function saveBatchImportConfig(payload: MobileToolsResponse['scanImport']) {
  return fetchJson('/api/local-batch-import/config', {
    method: 'POST',
    body: JSON.stringify({
      local_batch_import: {
        enabled: payload.enabled,
        watch_dirs: payload.watchDirs,
        processed_dir_name: payload.processedDirName,
        failed_dir_name: payload.failedDirName,
        scan_interval_seconds: payload.scanIntervalSeconds,
        notify_on_finish: payload.notifyOnFinish,
        duplicate_policy: payload.duplicatePolicy,
      },
    }),
  });
}

export async function saveOrganizerConfig(payload: MobileToolsResponse['organizer']) {
  return fetchJson('/api/local-3mf-organizer/config', {
    method: 'POST',
    body: JSON.stringify({
      local_3mf_organizer: {
        root_dir: payload.rootDir,
        mode: payload.mode,
      },
    }),
  });
}

export async function runScanImport(paths: string[]) {
  return fetchJson<ScanImportRunResponse>('/api/local-batch-import/run', {
    method: 'POST',
    body: JSON.stringify({
      paths,
      source_label: 'manual',
      force: true,
    }),
  });
}

export async function runOrganizer(payload: { rootDir: string; mode?: string }) {
  return fetchJson<OrganizerRunResponse>('/api/local-3mf-organizer/run', {
    method: 'POST',
    body: JSON.stringify({
      root_dir: payload.rootDir,
      mode: payload.mode || 'move',
      dry_run: false,
    }),
  });
}
