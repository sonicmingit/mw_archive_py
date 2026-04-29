export interface MobileQuickAction {
  key: string;
  label: string;
  path: string;
}

export interface MobileLibraryItem {
  id: string;
  modelId?: string;
  title: string;
  author: string;
  coverImage: string;
  isFavorite: boolean;
  isPrinted: boolean;
  isMissing: boolean;
  instanceCount: number;
  description?: string;
  tags?: string[];
  source?: string;
  createdAt?: string;
  publishedAt?: string;
  favoriteFolders?: string[];
}

export interface MobileOverviewResponse {
  stats: {
    totalModels: number;
    favoriteModels: number;
    printedModels: number;
    missingFiles: number;
    archiveQueue: number;
  };
  recentModels: MobileLibraryItem[];
  quickActions: MobileQuickAction[];
}

export interface MobileLibraryResponse {
  items: MobileLibraryItem[];
}

export interface GalleryFolder {
  id: string;
  name: string;
  description?: string;
  modelDirs: string[];
  createdAt?: string;
  updatedAt?: string;
}

export interface GalleryFlags {
  favorites: string[];
  printed: string[];
  folders: GalleryFolder[];
}

export interface MobileArchiveTask {
  id: string;
  url: string;
  status: 'running' | 'pending' | 'completed' | 'failed';
  title?: string;
  error?: string;
  progress?: number | null;
  time: string;
  message?: string;
}

export interface MobileMissingFile {
  model_id?: string;
  name?: string;
  model_name?: string;
  title?: string;
  error?: string;
  status?: string;
  url?: string;
  time?: string;
  inst_id?: string;
  base_name?: string;
}

export interface MobileArchiveCenterResponse {
  queue: MobileArchiveTask[];
  recentTasks: MobileArchiveTask[];
  missingFiles: MobileMissingFile[];
}

export interface MobileAttachment {
  id: string;
  name: string;
  type: '3mf' | 'stl' | 'pdf' | 'image' | 'file';
  url?: string;
  previewUrl?: string;
  downloadUrl?: string;
}

export interface MobilePlate {
  id: string;
  name: string;
  image: string;
  time: string;
  weight: string;
  materials: string[];
}

export interface MobileInstance {
  id: string;
  name: string;
  image?: string;
  downloadUrl?: string;
  time: string;
  weight: string;
  material: string;
  printer: string;
  layerHeight?: string;
  summary?: string;
  plates?: MobilePlate[];
}

export interface MobileModelDetail {
  id: string;
  title: string;
  author: string;
  coverImage: string;
  images?: string[];
  description?: string;
  descriptionHtml?: string;
  source?: string;
  createdAt?: string;
  sourceUrl?: string;
  tags?: string[];
  attachments?: MobileAttachment[];
  instances?: MobileInstance[];
}

export interface MobileArchiveCreateResponse {
  status: string;
  message?: string;
  task?: {
    task_id?: string;
    url?: string;
    status?: string;
    created_at?: string;
  };
  deduplicated?: boolean;
}

export interface MobileSettingsResponse {
  connection: {
    backendUrl: string;
  };
  notifications: {
    telegram: {
      enabled: boolean;
      botToken: string;
      chatId: string;
    };
    feishu: {
      enabled: boolean;
      webhookUrl: string;
    };
    wecom: {
      enabled: boolean;
      enableCommand: boolean;
    };
  };
  cookies: {
    cnCount: number;
    globalCount: number;
    cnStatus: string[];
    globalStatus: string[];
  };
}

export interface MobileToolsResponse {
  scanImport: {
    enabled: boolean;
    watchDirs: string[];
    processedDirName: string;
    failedDirName: string;
    scanIntervalSeconds: number;
    notifyOnFinish: boolean;
    duplicatePolicy: string;
  };
  organizer: {
    rootDir: string;
    mode: string;
  };
}

export interface CookieStoreEntry {
  value?: string;
  status?: string;
  name?: string;
}

export interface CookieStoreResponse {
  multi_cookie_enabled: boolean;
  cookie_store: {
    cn?: CookieStoreEntry[];
    global?: CookieStoreEntry[];
  };
  cookie_file?: string;
}

export interface ScanImportRunResponse {
  processed?: number;
  imported?: number;
  skipped?: number;
  failed?: number;
  details?: Array<Record<string, unknown>>;
}

export interface OrganizerRunResponse {
  processed?: number;
  moved?: number;
  copied?: number;
  failed?: number;
  duplicate_count?: number;
}
