const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, '');
}

export function getApiBaseUrl() {
  const stored = typeof window !== 'undefined' ? window.localStorage.getItem('mw_api_base_url') : '';
  const candidate = (stored || '').trim();
  if (candidate) {
    return trimTrailingSlash(candidate);
  }
  if (typeof window !== 'undefined') {
    const { origin, port, protocol } = window.location;
    if (protocol.startsWith('http') && (port === '8000' || port === '8001')) {
      return trimTrailingSlash(origin);
    }
  }
  return DEFAULT_API_BASE_URL;
}

export function setApiBaseUrl(value: string) {
  if (typeof window === 'undefined') {
    return;
  }
  const normalized = trimTrailingSlash((value || '').trim());
  if (!normalized) {
    window.localStorage.removeItem('mw_api_base_url');
    return;
  }
  window.localStorage.setItem('mw_api_base_url', normalized);
}

export function resolveApiUrl(path: string) {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${getApiBaseUrl()}${normalizedPath}`;
}

export function resolveAssetUrl(path?: string) {
  const raw = (path || '').trim();
  if (!raw) {
    return '';
  }
  if (/^(https?:)?\/\//i.test(raw) || raw.startsWith('data:') || raw.startsWith('blob:')) {
    return raw;
  }
  return resolveApiUrl(raw);
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(resolveApiUrl(path), {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
    ...init,
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message =
      (data && typeof data.detail === 'string' && data.detail) ||
      (data && typeof data.message === 'string' && data.message) ||
      `请求失败 (${response.status})`;
    throw new ApiError(message, response.status);
  }

  return data as T;
}
