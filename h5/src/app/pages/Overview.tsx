import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { 
  DownloadCloud, Library as LibraryIcon, ScanLine, FolderSync,
  ChevronRight
} from 'lucide-react';
import { getOverview } from '../lib/mobile-api';
import type { MobileLibraryItem, MobileOverviewResponse } from '../types/mobile';

export function Overview() {
  const [data, setData] = useState<MobileOverviewResponse | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setIsLoading(true);
    setError('');

    getOverview()
      .then((payload) => {
        if (!alive) {
          return;
        }
        setData(payload);
      })
      .catch((err: unknown) => {
        if (!alive) {
          return;
        }
        setError(err instanceof Error ? err.message : '加载失败，请稍后重试');
      })
      .finally(() => {
        if (alive) {
          setIsLoading(false);
        }
      });

    return () => {
      alive = false;
    };
  }, []);

  const quickActions = [
    { icon: DownloadCloud, label: '一键归档', to: '/archive', color: 'bg-blue-600 text-white' },
    { icon: LibraryIcon, label: '模型库', to: '/library', color: 'bg-slate-100 text-slate-700' },
    { icon: ScanLine, label: '扫描导入', to: '/scan', color: 'bg-slate-100 text-slate-700' },
    { icon: FolderSync, label: '整理目录', to: '/organize', color: 'bg-slate-100 text-slate-700' },
  ];

  const recentModels = data?.recentModels || [];
  const totalModels = data?.stats.totalModels ?? 0;

  const renderRecentModel = (model: MobileLibraryItem) => (
    <Link key={model.id} to={`/model/${model.id}`} className="flex items-start gap-4 p-4 active:bg-slate-50 dark:active:bg-slate-800/60 transition-colors">
      <img src={model.coverImage || '/h5/icons/icon-192.png'} alt={model.title} className="w-20 h-20 rounded-xl object-cover bg-slate-100 dark:bg-slate-800 shrink-0" />
      <div className="flex-1 min-w-0">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug line-clamp-2">{model.title}</h3>
        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
          {model.source && (
            <span className="text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-2 py-0.5 rounded font-medium border border-slate-200 dark:border-slate-700">
              {model.source}
            </span>
          )}
          {model.createdAt && (
            <span className="text-[10px] text-slate-400 dark:text-slate-500 font-medium">
              {model.createdAt.split('T')[0].split(' ')[0]}
            </span>
          )}
        </div>
      </div>
    </Link>
  );

  return (
    <div className="flex flex-col min-h-full bg-slate-50 dark:bg-slate-950 transition-colors">
      {/* Header */}
      <header className="px-5 pt-12 pb-4 bg-white dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 transition-colors">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">本地模型库</h1>
        {data && <span className="text-sm text-slate-600 dark:text-slate-300">{totalModels} 个模型</span>}
      </header>

      <div className="p-5 space-y-6">
        {/* Quick Actions */}
        <section>
          <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-3 px-1">快捷操作</h2>
          <div className="grid grid-cols-4 gap-3">
            {quickActions.map((action, idx) => (
              <Link key={idx} to={action.to} className="flex flex-col items-center gap-2 group">
                <div className={`w-14 h-14 rounded-[1.25rem] flex items-center justify-center shadow-sm transition-transform active:scale-95 ${action.color}`}>
                  <action.icon size={24} />
                </div>
                <span className="text-[11px] font-medium text-slate-600 dark:text-slate-400">{action.label}</span>
              </Link>
            ))}
          </div>
        </section>

        {/* Recent Updates */}
        <section>
          <div className="flex items-center justify-between mb-3 px-1">
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">最近更新</h2>
            <Link to="/library" className="text-xs font-medium text-blue-600 flex items-center">
              全部 <ChevronRight size={14} />
            </Link>
          </div>
          <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800 overflow-hidden divide-y divide-slate-100 dark:divide-slate-800 transition-colors">
            {isLoading && (
              <div className="p-6 text-sm text-slate-400 dark:text-slate-500 text-center">正在加载最近更新...</div>
            )}
            {!isLoading && error && (
              <div className="p-6 text-sm text-rose-600 text-center">{error}</div>
            )}
            {!isLoading && !error && recentModels.length === 0 && (
              <div className="p-6 text-sm text-slate-400 dark:text-slate-500 text-center">当前还没有可展示的模型</div>
            )}
            {!isLoading && !error && recentModels.map(renderRecentModel)}
          </div>
        </section>
      </div>
    </div>
  );
}
