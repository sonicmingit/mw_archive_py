const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

function isAbsolute(url) {
  return /^https?:\/\//i.test(url);
}

export function buildApiUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return isAbsolute(API_BASE_URL) ? `${API_BASE_URL}${normalizedPath}` : `${API_BASE_URL}${normalizedPath}`;
}

export async function fetchJson(path, options = {}) {
  const response = await fetch(buildApiUrl(path), options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export function encodeRelativePath(relPath) {
  return String(relPath || '')
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}

export function modelFileUrl(modelDir, relPath) {
  return buildApiUrl(`/models/${encodeURIComponent(modelDir)}/file/${encodeRelativePath(relPath)}`);
}

export function instanceDownloadUrl(modelDir, instanceId) {
  return buildApiUrl(`/models/${encodeURIComponent(modelDir)}/instances/${instanceId}/download`);
}
