const API_BASE_STORAGE_KEY = 'mw_api_base_url';

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, '');
}

function isLoopbackHost(hostname: string) {
  const raw = (hostname || '').trim().toLowerCase();
  return raw === '127.0.0.1' || raw === 'localhost' || raw === '::1';
}

function getCurrentOriginBase() {
  if (typeof window === 'undefined') {
    return '';
  }
  const { origin, protocol } = window.location;
  if (protocol.startsWith('http')) {
    return trimTrailingSlash(origin);
  }
  return '';
}

function pickStoredApiBase() {
  if (typeof window === 'undefined') {
    return '';
  }
  const candidate = (window.localStorage.getItem(API_BASE_STORAGE_KEY) || '').trim();
  if (!candidate) {
    return '';
  }
  try {
    const parsed = new URL(candidate);
    const current = new URL(window.location.origin);
    const currentIsLoopback = isLoopbackHost(current.hostname);
    const storedIsLoopback = isLoopbackHost(parsed.hostname);
    if (storedIsLoopback && !currentIsLoopback) {
      return '';
    }
    return trimTrailingSlash(parsed.origin);
  } catch {
    return '';
  }
}

export function getApiBaseUrl() {
  const storedBase = pickStoredApiBase();
  if (storedBase) {
    return storedBase;
  }
  return getCurrentOriginBase();
}

export function setApiBaseUrl(value: string) {
  if (typeof window === 'undefined') {
    return;
  }
  const normalized = trimTrailingSlash((value || '').trim());
  if (!normalized) {
    window.localStorage.removeItem(API_BASE_STORAGE_KEY);
    return;
  }
  const currentOrigin = getCurrentOriginBase();
  if (currentOrigin && normalized === currentOrigin) {
    window.localStorage.removeItem(API_BASE_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(API_BASE_STORAGE_KEY, normalized);
}

export function resolveApiUrl(path: string) {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const base = getApiBaseUrl();
  return base ? `${base}${normalizedPath}` : normalizedPath;
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
