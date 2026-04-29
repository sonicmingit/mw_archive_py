import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router';
import { 
  Search, ChevronDown, LayoutGrid, List as ListIcon, 
  MoreVertical, Clock, Box, X, FolderHeart, AlertCircle, Trash2, Check
} from 'lucide-react';
import { getGalleryFlags, getLibrary, saveGalleryFlags } from '../lib/mobile-api';
import type { GalleryFlags, MobileLibraryItem } from '../types/mobile';
import clsx from 'clsx';

const LIBRARY_REFRESH_EVENT = 'mw:library-refresh';
const ALL_FILTER_VALUE = '__all__';
const FAVORITES_FILTER_VALUE = '__favorites__';

type FilterType = 'source' | 'favorites' | 'author' | 'tags';

type FilterOption = {
  label: string;
  value: string;
};

// A helper wrapper to ensure modals stay within the mobile prototype bounds
const ModalWrapper = ({ isOpen, onClose, children }: { isOpen: boolean; onClose: () => void; children: React.ReactNode }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-[100] flex justify-center bg-black/40 backdrop-blur-sm animate-in fade-in duration-200" onClick={onClose}>
      <div className="w-full max-w-md relative flex flex-col justify-end pb-[68px]" onClick={e => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
};

export function Library() {
  const location = useLocation();
  const [isCompact, setIsCompact] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'archive' | 'published'>('archive');
  const [models, setModels] = useState<MobileLibraryItem[]>([]);
  const [galleryFlags, setGalleryFlags] = useState<GalleryFlags>({ favorites: [], printed: [], folders: [] });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  
  // Filter state
  const [activeFilterDrawer, setActiveFilterDrawer] = useState<FilterType | null>(null);
  const [selectedFilters, setSelectedFilters] = useState<Record<FilterType, string>>({
    source: ALL_FILTER_VALUE,
    favorites: ALL_FILTER_VALUE,
    author: ALL_FILTER_VALUE,
    tags: ALL_FILTER_VALUE,
  });
  
  // Context Menu state
  const [activeMenuModel, setActiveMenuModel] = useState<MobileLibraryItem | null>(null);
  const [showFavoritesModal, setShowFavoritesModal] = useState<MobileLibraryItem | null>(null);
  const [favoriteEnabled, setFavoriteEnabled] = useState(false);
  const [selectedFolderIds, setSelectedFolderIds] = useState<string[]>([]);
  const [newFolderName, setNewFolderName] = useState('');
  const [favoriteError, setFavoriteError] = useState('');
  const [isSavingFavorite, setIsSavingFavorite] = useState(false);

  const hasActiveFilters =
    searchQuery.trim().length > 0 ||
    Object.values(selectedFilters).some((value) => value !== ALL_FILTER_VALUE);

  useEffect(() => {
    let alive = true;

    const load = async (showLoading: boolean, refresh = true) => {
      if (showLoading) {
        setIsLoading(true);
      } else {
        setIsRefreshing(true);
      }
      setError('');

      try {
        const [payload, flags] = await Promise.all([
          getLibrary({ refresh }),
          getGalleryFlags(),
        ]);
        if (!alive) {
          return;
        }
        setModels(payload.items || []);
        setGalleryFlags(flags);
      } catch (err: unknown) {
        if (!alive) {
          return;
        }
        setError(err instanceof Error ? err.message : '加载失败，请稍后重试');
      } finally {
        if (!alive) {
          return;
        }
        if (showLoading) {
          setIsLoading(false);
        } else {
          setIsRefreshing(false);
        }
      }
    };

    void load(models.length === 0, true);

    const handleRefresh = () => {
      void load(false, true);
    };

    window.addEventListener(LIBRARY_REFRESH_EVENT, handleRefresh);

    return () => {
      alive = false;
      window.removeEventListener(LIBRARY_REFRESH_EVENT, handleRefresh);
    };
  }, [location.key]);

  const filterOptions: Record<FilterType, FilterOption[]> = {
    source: [
      { label: '全部', value: ALL_FILTER_VALUE },
      ...Array.from(new Set(models.map((model) => (model.source || '').trim()).filter(Boolean)))
        .sort((a, b) => a.localeCompare(b, 'zh-CN'))
        .map((source) => ({ label: source, value: source })),
    ],
    favorites: [
      { label: '全部', value: ALL_FILTER_VALUE },
      { label: '已收藏', value: FAVORITES_FILTER_VALUE },
      ...(galleryFlags.folders || []).map((folder) => ({
        label: folder.name,
        value: folder.id,
      })),
    ],
    author: [
      { label: '全部', value: ALL_FILTER_VALUE },
      ...Array.from(new Set(models.map((model) => (model.author || '').trim()).filter(Boolean)))
        .sort((a, b) => a.localeCompare(b, 'zh-CN'))
        .map((author) => ({ label: author, value: author })),
    ],
    tags: [
      { label: '全部', value: ALL_FILTER_VALUE },
      ...Array.from(
        new Set(
          models.flatMap((model) =>
            (model.tags || []).map((tag) => String(tag || '').trim()).filter(Boolean),
          ),
        ),
      )
        .sort((a, b) => a.localeCompare(b, 'zh-CN'))
        .map((tag) => ({ label: tag, value: tag })),
    ],
  };

  const getFilterButtonLabel = (type: FilterType, defaultLabel: string) => {
    const selectedValue = selectedFilters[type];
    const selected = filterOptions[type].find((option) => option.value === selectedValue);
    return selected && selected.value !== ALL_FILTER_VALUE ? selected.label : defaultLabel;
  };

  const filteredModels = models
    .filter((model) => {
      const query = searchQuery.trim().toLowerCase();
      if (
        query &&
        ![
          model.title,
          model.author,
          model.source,
          ...(model.tags || []),
        ]
          .join(' ')
          .toLowerCase()
          .includes(query)
      ) {
        return false;
      }

      if (selectedFilters.source !== ALL_FILTER_VALUE && model.source !== selectedFilters.source) {
        return false;
      }

      if (selectedFilters.author !== ALL_FILTER_VALUE && model.author !== selectedFilters.author) {
        return false;
      }

      if (selectedFilters.tags !== ALL_FILTER_VALUE && !(model.tags || []).includes(selectedFilters.tags)) {
        return false;
      }

      if (selectedFilters.favorites === FAVORITES_FILTER_VALUE && !model.isFavorite) {
        return false;
      }

      if (
        selectedFilters.favorites !== ALL_FILTER_VALUE &&
        selectedFilters.favorites !== FAVORITES_FILTER_VALUE
      ) {
        const targetFolder = (galleryFlags.folders || []).find((folder) => folder.id === selectedFilters.favorites);
        if (!targetFolder || !targetFolder.modelDirs.includes(model.id)) {
          return false;
        }
      }

      return true;
    })
    .sort((a, b) => {
      const archiveTimeA = Date.parse(a.createdAt || '') || 0;
      const archiveTimeB = Date.parse(b.createdAt || '') || 0;
      const publishedTimeA = Date.parse(a.publishedAt || '') || 0;
      const publishedTimeB = Date.parse(b.publishedAt || '') || 0;

      if (sortBy === 'published') {
        return publishedTimeB - publishedTimeA || archiveTimeB - archiveTimeA;
      }

      return archiveTimeB - archiveTimeA || publishedTimeB - publishedTimeA;
    });

  const FilterButton = ({ type, label }: { type: FilterType, label: string }) => (
    <button
      onClick={() => setActiveFilterDrawer(type)}
      className="px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-900 text-slate-700 dark:text-slate-300 text-[11px] font-medium flex items-center gap-1 shrink-0 hover:bg-slate-200 dark:hover:bg-slate-800 active:scale-95 transition-all"
    >
      <span className="truncate max-w-[92px]">{getFilterButtonLabel(type, label)}</span>
      <ChevronDown size={14} className="text-slate-400 dark:text-slate-500 shrink-0" />
    </button>
  );

  const openFavoritesModal = (model: MobileLibraryItem | null) => {
    if (!model) {
      return;
    }
    const linkedFolders = (galleryFlags.folders || [])
      .filter((folder) => folder.modelDirs.includes(model.id))
      .map((folder) => folder.id);
    setShowFavoritesModal(model);
    setFavoriteEnabled(Boolean(model.isFavorite || linkedFolders.length > 0));
    setSelectedFolderIds(linkedFolders);
    setNewFolderName('');
    setFavoriteError('');
  };

  const closeFavoritesModal = () => {
    setShowFavoritesModal(null);
    setFavoriteEnabled(false);
    setSelectedFolderIds([]);
    setNewFolderName('');
    setFavoriteError('');
    setIsSavingFavorite(false);
  };

  const toggleFolderSelection = (folderId: string) => {
    setSelectedFolderIds((current) =>
      current.includes(folderId) ? current.filter((id) => id !== folderId) : [...current, folderId],
    );
  };

  const createFolderId = () => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    return `folder-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  };

  const handleSaveFavorites = async () => {
    if (!showFavoritesModal) {
      return;
    }

    const modelId = showFavoritesModal.id;
    const folderName = newFolderName.trim();
    const existingFolderNames = new Set((galleryFlags.folders || []).map((folder) => folder.name.toLowerCase()));

    if (folderName && existingFolderNames.has(folderName.toLowerCase())) {
      setFavoriteError('收藏夹名称已存在');
      return;
    }

    setIsSavingFavorite(true);
    setFavoriteError('');

    const nextFolders = (galleryFlags.folders || []).map((folder) => {
      const included = selectedFolderIds.includes(folder.id);
      const nextModelDirs = included
        ? Array.from(new Set([...folder.modelDirs, modelId]))
        : folder.modelDirs.filter((item) => item !== modelId);
      return {
        ...folder,
        modelDirs: nextModelDirs,
        updatedAt: new Date().toISOString(),
      };
    });

    if (folderName) {
      nextFolders.push({
        id: createFolderId(),
        name: folderName,
        description: '',
        modelDirs: [modelId],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      });
    }

    const hasFolderSelection = nextFolders.some((folder) => folder.modelDirs.includes(modelId));
    const shouldFavorite = favoriteEnabled || hasFolderSelection;
    const nextFavorites = shouldFavorite
      ? Array.from(new Set([...(galleryFlags.favorites || []), modelId]))
      : (galleryFlags.favorites || []).filter((item) => item !== modelId);

    const nextFlags: GalleryFlags = {
      favorites: nextFavorites,
      printed: galleryFlags.printed || [],
      folders: nextFolders,
    };

    try {
      await saveGalleryFlags(nextFlags);
      setGalleryFlags(nextFlags);
      setModels((current) =>
        current.map((model) =>
          model.id === modelId
            ? {
                ...model,
                isFavorite: shouldFavorite,
                favoriteFolders: nextFolders
                  .filter((folder) => folder.modelDirs.includes(modelId))
                  .map((folder) => folder.name),
              }
            : model,
        ),
      );
      closeFavoritesModal();
    } catch (err: unknown) {
      setFavoriteError(err instanceof Error ? err.message : '收藏保存失败，请稍后重试');
      setIsSavingFavorite(false);
    }
  };

  const resetFilters = () => {
    setSearchQuery('');
    setSelectedFilters({
      source: ALL_FILTER_VALUE,
      favorites: ALL_FILTER_VALUE,
      author: ALL_FILTER_VALUE,
      tags: ALL_FILTER_VALUE,
    });
  };

  return (
    <div className="flex flex-col min-h-full bg-slate-50 dark:bg-slate-950 relative pb-20 transition-colors">
      {/* Header */}
      <header className="bg-white dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 px-5 pt-12 pb-3 sticky top-0 z-10 transition-colors">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-xl font-bold text-slate-900 dark:text-white tracking-tight">模型库</h1>
          <div className="flex items-center gap-2">
            {isRefreshing && (
              <span className="text-[11px] text-slate-400 dark:text-slate-500 font-medium">更新中...</span>
            )}
            <button 
              onClick={() => setIsCompact(!isCompact)}
              className="w-8 h-8 rounded-full bg-slate-50 dark:bg-slate-900 flex items-center justify-center text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              {isCompact ? <ListIcon size={18} /> : <LayoutGrid size={18} />}
            </button>
          </div>
        </div>
        
        {/* Search Bar */}
        <div className="relative flex items-center mb-4">
          <Search className="absolute left-3 text-slate-400 dark:text-slate-500" size={18} />
          <input 
            type="text" 
            placeholder="搜索模型、作者、标签..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-100 dark:bg-slate-900 text-slate-900 dark:text-slate-100 text-sm rounded-xl py-2.5 pl-10 pr-4 outline-none focus:ring-2 focus:ring-blue-500 transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500"
          />
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 hide-scrollbar">
          <FilterButton type="source" label="来源" />
          <FilterButton type="favorites" label="收藏夹" />
          <FilterButton type="author" label="作者" />
          <FilterButton type="tags" label="标签" />
          {hasActiveFilters && (
            <button
              onClick={resetFilters}
              className="px-3 py-1.5 rounded-lg bg-rose-50 text-rose-600 text-[11px] font-medium shrink-0 hover:bg-rose-100 active:scale-95 transition-all border border-rose-100"
            >
              重置
            </button>
          )}
        </div>

        <div className="mt-3 flex items-center gap-2 overflow-x-auto pb-1 hide-scrollbar">
          <span className="text-[11px] font-semibold text-slate-400 shrink-0">排序</span>
          <button
            onClick={() => setSortBy('archive')}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-[11px] font-medium shrink-0 transition-all',
              sortBy === 'archive'
                ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-100 dark:border-blue-500/20'
                : 'bg-slate-100 dark:bg-slate-900 text-slate-600 dark:text-slate-300 border border-transparent hover:bg-slate-200 dark:hover:bg-slate-800',
            )}
          >
            归档时间
          </button>
          <button
            onClick={() => setSortBy('published')}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-[11px] font-medium shrink-0 transition-all',
              sortBy === 'published'
                ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-100 dark:border-blue-500/20'
                : 'bg-slate-100 dark:bg-slate-900 text-slate-600 dark:text-slate-300 border border-transparent hover:bg-slate-200 dark:hover:bg-slate-800',
            )}
          >
            发布时间
          </button>
        </div>
      </header>

      {/* List / Grid */}
      <div className={clsx("p-4 gap-3", isCompact ? "grid grid-cols-3" : "grid grid-cols-2")}>
        {isLoading ? (
          <div className={clsx("flex flex-col items-center justify-center py-20 text-slate-400", isCompact ? "col-span-3" : "col-span-2")}>
            <Box size={48} className="mb-4 opacity-50" />
            <p className="text-sm font-medium">模型加载中...</p>
          </div>
        ) : error ? (
          <div className={clsx("flex flex-col items-center justify-center py-20 text-rose-500", isCompact ? "col-span-3" : "col-span-2")}>
            <AlertCircle size={48} className="mb-4 opacity-80" />
            <p className="text-sm font-medium">{error}</p>
          </div>
        ) : filteredModels.length > 0 ? (
          filteredModels.map(model => (
            <div key={model.id} className="relative group bg-white dark:bg-slate-900 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800 overflow-hidden flex flex-col transition-transform">
              <Link to={`/model/${model.id}`} className="block bg-slate-100 dark:bg-slate-800 relative aspect-square overflow-hidden">
                <img
                  src={model.coverImage || 'https://placehold.co/320x320/e2e8f0/64748b?text=3D'}
                  alt={model.title}
                  className="w-full h-full object-cover object-center"
                />
                {model.isMissing && !isCompact && (
                  <div className="absolute top-2 right-2 bg-red-500/90 backdrop-blur text-white p-1.5 rounded-lg shadow-sm">
                    <AlertCircle size={14} />
                  </div>
                )}
              </Link>
              
              {isCompact ? (
                <div className="p-2">
                  <h3 className="text-[10px] font-semibold text-slate-800 dark:text-slate-100 line-clamp-1 leading-snug">{model.title}</h3>
                </div>
              ) : (
                <div className="p-3 flex-1 flex flex-col">
                  <div className="flex items-start justify-between gap-1 mb-1">
                    <Link to={`/model/${model.id}`} className="flex-1">
                      <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 line-clamp-2 leading-snug">{model.title}</h3>
                    </Link>
                    <button 
                      onClick={(e) => { e.preventDefault(); setActiveMenuModel(model); }}
                      className="w-6 h-6 rounded-full flex items-center justify-center text-slate-400 dark:text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-200 active:scale-90 transition-all shrink-0 -mt-0.5 -mr-1"
                    >
                      <MoreVertical size={16} />
                    </button>
                  </div>
                  
                  <div className="mt-auto flex flex-wrap gap-1.5 pt-2">
                    <span className="text-[9px] bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-1.5 py-0.5 rounded-md font-semibold flex items-center gap-1 border border-slate-100 dark:border-slate-700">
                      <Box size={10} /> {model.instanceCount} 实例
                    </span>
                    <span className="text-[9px] bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-1.5 py-0.5 rounded-md font-semibold flex items-center gap-1 border border-slate-100 dark:border-slate-700">
                      <Clock size={10} /> {(sortBy === 'published' ? model.publishedAt : model.createdAt)?.split('T')[0]?.split(' ')[0] || '未知时间'}
                    </span>
                    {model.isFavorite && (
                      <span className="text-[9px] bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-300 px-1.5 py-0.5 rounded-md font-semibold flex items-center gap-1 border border-rose-100 dark:border-rose-500/20">
                        <FolderHeart size={10} /> 已收藏
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))
        ) : (
          <div className={clsx("flex flex-col items-center justify-center py-20 text-slate-400", isCompact ? "col-span-3" : "col-span-2")}>
            <Box size={48} className="mb-4 opacity-50" />
            <p className="text-sm font-medium">没有找到匹配的模型</p>
          </div>
        )}
      </div>

      {/* Filter Drawer */}
      <ModalWrapper isOpen={!!activeFilterDrawer} onClose={() => setActiveFilterDrawer(null)}>
        <div className="bg-white dark:bg-slate-900 w-full rounded-t-3xl overflow-hidden animate-in slide-in-from-bottom-full duration-300 transition-colors">
          <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <h3 className="font-bold text-slate-900 dark:text-white text-lg">
              {activeFilterDrawer === 'source' && '选择来源'}
              {activeFilterDrawer === 'favorites' && '选择收藏夹'}
              {activeFilterDrawer === 'author' && '选择作者'}
              {activeFilterDrawer === 'tags' && '选择标签'}
            </h3>
            <button onClick={() => setActiveFilterDrawer(null)} className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
              <X size={18} />
            </button>
          </div>
          <div className="p-5 max-h-[50vh] overflow-y-auto space-y-2">
            {activeFilterDrawer && filterOptions[activeFilterDrawer].map((opt) => (
              <button 
                key={opt.value}
                onClick={() => {
                  if (!activeFilterDrawer) {
                    return;
                  }
                  setSelectedFilters((current) => ({
                    ...current,
                    [activeFilterDrawer]: opt.value,
                  }));
                  setActiveFilterDrawer(null);
                }}
                className={clsx(
                  'w-full text-left px-4 py-3 rounded-xl text-sm font-medium transition-colors flex items-center justify-between gap-3',
                  selectedFilters[activeFilterDrawer] === opt.value
                    ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400'
                    : 'hover:bg-slate-50 dark:hover:bg-slate-800 active:bg-slate-100 dark:active:bg-slate-800 text-slate-700 dark:text-slate-200',
                )}
              >
                <span>{opt.label}</span>
                {selectedFilters[activeFilterDrawer] === opt.value && <Check size={16} />}
              </button>
            ))}
          </div>
        </div>
      </ModalWrapper>

      {/* Context Menu Modal */}
      <ModalWrapper isOpen={!!activeMenuModel} onClose={() => setActiveMenuModel(null)}>
        <div className="bg-white dark:bg-slate-900 w-full rounded-t-3xl overflow-hidden pb-safe animate-in slide-in-from-bottom-full duration-300 transition-colors">
          <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex gap-3 items-center">
            {activeMenuModel && <img src={activeMenuModel.coverImage} alt="" className="w-12 h-12 rounded-lg object-cover object-center" />}
            <div className="flex-1 min-w-0">
              <h3 className="font-bold text-slate-900 dark:text-white text-sm truncate">{activeMenuModel?.title}</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">选项与管理</p>
            </div>
            <button onClick={() => setActiveMenuModel(null)} className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 shrink-0">
              <X size={18} />
            </button>
          </div>
          
          <div className="p-2 space-y-1">
            <button 
              onClick={() => {
                openFavoritesModal(activeMenuModel);
                setActiveMenuModel(null);
              }}
              className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-slate-50 dark:hover:bg-slate-800 active:bg-slate-100 dark:active:bg-slate-800 rounded-xl text-sm font-medium text-slate-700 dark:text-slate-200 transition-colors"
            >
              <FolderHeart size={18} className="text-rose-500" /> 收藏管理
            </button>
            <button className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-rose-50 active:bg-rose-100 rounded-xl text-sm font-medium text-rose-600 transition-colors mt-2">
              <Trash2 size={18} /> 删除模型
            </button>
          </div>
        </div>
      </ModalWrapper>

      {/* Favorites Management Modal */}
      <ModalWrapper isOpen={!!showFavoritesModal} onClose={() => setShowFavoritesModal(null)}>
        <div className="bg-white dark:bg-slate-900 w-full rounded-t-3xl overflow-hidden animate-in slide-in-from-bottom-full duration-300 max-h-[calc(100dvh-24px)] flex flex-col transition-colors">
          <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <h3 className="font-bold text-slate-900 dark:text-white text-lg">收藏管理</h3>
            <button onClick={closeFavoritesModal} className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
              <X size={18} />
            </button>
          </div>
          
          <div className="flex-1 overflow-y-auto p-5 space-y-3 min-h-0">
            <label className="flex items-center gap-3 p-3 rounded-xl border border-rose-100 dark:border-rose-500/20 bg-rose-50/60 dark:bg-rose-500/10 cursor-pointer transition-colors">
              <input
                type="checkbox"
                checked={favoriteEnabled}
                onChange={(e) => setFavoriteEnabled(e.target.checked)}
                className="w-5 h-5 rounded border-slate-300 text-rose-500 focus:ring-rose-500"
              />
              <div className="flex items-center gap-2">
                <FolderHeart size={16} className="text-rose-500" />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-100">加入总收藏</span>
              </div>
            </label>

            {(galleryFlags.folders || []).map((folder) => (
              <label key={folder.id} className="flex items-center gap-3 p-3 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 border border-slate-100 dark:border-slate-800 cursor-pointer transition-colors">
                <input 
                  type="checkbox"
                  checked={selectedFolderIds.includes(folder.id)}
                  onChange={() => toggleFolderSelection(folder.id)}
                  className="w-5 h-5 rounded border-slate-300 text-rose-500 focus:ring-rose-500" 
                />
                <div className="flex items-center gap-2 min-w-0">
                  <FolderHeart size={16} className="text-slate-400 shrink-0" />
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-100 truncate">{folder.name}</span>
                </div>
              </label>
            ))}

            <div className="space-y-2 pt-1">
              <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400">新建收藏夹</label>
              <input
                type="text"
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                placeholder="输入新的收藏夹名称"
                className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-rose-500 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500"
              />
            </div>

            {favoriteError && (
              <div className="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                {favoriteError}
              </div>
            )}
          </div>

          <div className="p-5 pt-3 border-t border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 pb-[max(env(safe-area-inset-bottom),20px)] shrink-0">
            <button 
              onClick={handleSaveFavorites}
              disabled={isSavingFavorite}
              className="w-full bg-rose-600 hover:bg-rose-700 active:bg-rose-800 disabled:bg-rose-300 text-white font-semibold py-3.5 rounded-xl transition-colors"
            >
              {isSavingFavorite ? '保存中...' : '保存更改'}
            </button>
          </div>
        </div>
      </ModalWrapper>

      <style>{`
        .hide-scrollbar::-webkit-scrollbar {
          display: none;
        }
        .hide-scrollbar {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
        .pb-safe {
          padding-bottom: env(safe-area-inset-bottom, 20px);
        }
      `}</style>
    </div>
  );
}
