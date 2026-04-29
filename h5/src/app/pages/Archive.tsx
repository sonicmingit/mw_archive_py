import { useEffect, useState } from 'react';
import { DownloadCloud, CheckCircle, Clock, AlertCircle, Loader2, FileWarning, RefreshCw, ExternalLink, RefreshCcw } from 'lucide-react';
import { createArchiveTask, getArchiveCenter, redownloadMissingFiles } from '../lib/mobile-api';
import type { MobileArchiveTask, MobileMissingFile } from '../types/mobile';
import clsx from 'clsx';

export function Archive() {
  const [url, setUrl] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [tasks, setTasks] = useState<MobileArchiveTask[]>([]);
  const [recentTasks, setRecentTasks] = useState<MobileArchiveTask[]>([]);
  const [missingFiles, setMissingFiles] = useState<MobileMissingFile[]>([]);
  const [activeTab, setActiveTab] = useState<'queue' | 'missing'>('queue');
  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [submittedTaskId, setSubmittedTaskId] = useState('');

  const loadArchiveCenter = async () => {
    setError('');
    const payload = await getArchiveCenter();
    setTasks(payload.queue || []);
    setRecentTasks(payload.recentTasks || []);
    setMissingFiles(payload.missingFiles || []);
    return payload;
  };

  useEffect(() => {
    let alive = true;
    setIsLoading(true);
    setError('');

    getArchiveCenter()
      .then((payload) => {
        if (!alive) {
          return;
        }
        setTasks(payload.queue || []);
        setRecentTasks(payload.recentTasks || []);
        setMissingFiles(payload.missingFiles || []);
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

  useEffect(() => {
    const hasActiveTasks = tasks.some((task) => task.status === 'running' || task.status === 'pending');
    if (!hasActiveTasks && !submittedTaskId) {
      return;
    }

    const timer = window.setInterval(() => {
      loadArchiveCenter()
        .then((payload) => {
          const currentTasks = payload.queue || [];
          const currentRecentTasks = payload.recentTasks || [];
          if (submittedTaskId) {
            const matchedTask = [...currentTasks, ...currentRecentTasks].find((task) => task.id === submittedTaskId);
            if (matchedTask && matchedTask.status === 'completed') {
              setActionMessage(`归档完成：${matchedTask.title || '模型已入库'}`);
              setSubmittedTaskId('');
            } else if (matchedTask && matchedTask.status === 'failed') {
              setActionMessage(`归档失败：${matchedTask.error || matchedTask.message || '请查看任务详情'}`);
              setSubmittedTaskId('');
            }
          }
        })
        .catch(() => {
          // Polling should not interrupt the current view with noisy errors.
        });
    }, 3000);

    return () => window.clearInterval(timer);
  }, [tasks, submittedTaskId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url) return;
    
    setIsSubmitting(true);
    setActionMessage('');
    try {
      const result = await createArchiveTask(url);
      setUrl('');
      setActiveTab('queue');
      setSubmittedTaskId(result.task?.task_id || '');
      setActionMessage(result.deduplicated ? '相同链接已在队列中，已为你切到任务列表。' : '归档任务已提交，正在加入队列...');
      await loadArchiveCenter();
    } catch (err: unknown) {
      setActionMessage(err instanceof Error ? err.message : '归档提交失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRedownload = async (id: string) => {
    setRefreshingId(id);
    try {
      const result = await redownloadMissingFiles();
      setActionMessage(result.message || '已触发缺失文件重试下载');
      await loadArchiveCenter();
    } catch (err: unknown) {
      setActionMessage(err instanceof Error ? err.message : '重试下载失败');
    } finally {
      setRefreshingId(null);
    }
  };

  const handleRefresh = async () => {
    setIsLoading(true);
    setActionMessage('');
    try {
      await loadArchiveCenter();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '刷新失败，请稍后重试');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRedownloadAll = async () => {
    setRefreshingId('all');
    try {
      const result = await redownloadMissingFiles();
      setActionMessage(result.message || '已触发全部缺失文件重新下载');
      await loadArchiveCenter();
    } catch (err: unknown) {
      setActionMessage(err instanceof Error ? err.message : '重新下载失败');
    } finally {
      setRefreshingId(null);
    }
  };

  const displayTasks = tasks.length > 0 ? tasks : recentTasks;
  const activeTaskCount = tasks.filter((task) => task.status === 'running' || task.status === 'pending').length;
  const latestFinishedTask = recentTasks.find((task) => task.status === 'completed' || task.status === 'failed');

  const StatusIcon = ({ status }: { status: MobileArchiveTask['status'] }) => {
    switch (status) {
      case 'running': return <Loader2 size={16} className="text-blue-500 animate-spin" />;
      case 'pending': return <Clock size={16} className="text-amber-500" />;
      case 'completed': return <CheckCircle size={16} className="text-emerald-500" />;
      case 'failed': return <AlertCircle size={16} className="text-rose-500" />;
      default: return <Clock size={16} className="text-slate-400" />;
    }
  };

  return (
    <div className="flex flex-col min-h-full bg-slate-50 dark:bg-slate-950 pb-20 transition-colors">
      <header className="px-5 pt-12 pb-4 bg-white dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 sticky top-0 z-10 transition-colors">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white tracking-tight">归档中心</h1>
      </header>

      <div className="p-5 space-y-6">
        {/* Input Card */}
        <div className="bg-white dark:bg-slate-900 p-5 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800 relative overflow-hidden transition-colors">
          <div className="absolute top-0 right-0 w-32 h-32 bg-blue-50 dark:bg-blue-500/10 rounded-full blur-3xl -mr-10 -mt-10 opacity-60 pointer-events-none" />
          <form onSubmit={handleSubmit} className="space-y-4 relative">
            <div>
              <label className="block text-xs font-bold text-slate-800 dark:text-slate-200 mb-2">新建归档任务</label>
              <input
                type="text"
                placeholder="在此粘贴模型链接 (如 makerworld.com/...)"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors placeholder:text-slate-400 dark:placeholder:text-slate-500"
              />
            </div>
            <button
              type="submit"
              disabled={!url || isSubmitting}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 disabled:shadow-none shadow-sm shadow-blue-200 disabled:cursor-not-allowed text-white font-semibold py-3.5 rounded-xl flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
            >
              {isSubmitting ? <Loader2 size={18} className="animate-spin" /> : <DownloadCloud size={18} />}
              {isSubmitting ? '解析链接中...' : '开始归档提取'}
            </button>
          </form>
        </div>
        {actionMessage && (
          <div className="bg-blue-50 text-blue-700 text-sm font-medium px-4 py-3 rounded-2xl border border-blue-100">
            {actionMessage}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-white dark:bg-slate-900 p-4 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800 transition-colors">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">进行中</div>
            <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-white">{activeTaskCount}</div>
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">队列和运行中的归档任务</div>
          </div>
          <div className="bg-white dark:bg-slate-900 p-4 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800 transition-colors">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">最近结果</div>
            <div className="mt-2 text-sm font-bold text-slate-900 dark:text-white line-clamp-2">
              {latestFinishedTask?.title || latestFinishedTask?.message || '暂无完成记录'}
            </div>
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {latestFinishedTask ? (latestFinishedTask.status === 'completed' ? '最近一次归档已完成' : '最近一次归档失败') : '提交后会在这里显示结果'}
            </div>
          </div>
        </div>

        {/* Tabs & List */}
        <div>
          <div className="flex bg-slate-200/50 dark:bg-slate-800/80 p-1 rounded-xl mb-4 transition-colors">
            <button 
              onClick={() => setActiveTab('queue')}
              className={clsx(
                "flex-1 py-2 text-sm font-semibold rounded-lg transition-all",
                activeTab === 'queue' ? "bg-white dark:bg-slate-900 text-slate-800 dark:text-white shadow-sm" : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
              )}
            >
              任务队列
            </button>
            <button 
              onClick={() => setActiveTab('missing')}
              className={clsx(
                "flex-1 py-2 text-sm font-semibold rounded-lg transition-all flex items-center justify-center gap-1.5",
                activeTab === 'missing' ? "bg-white dark:bg-slate-900 text-slate-800 dark:text-white shadow-sm" : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
              )}
            >
              缺失文件
              {missingFiles.length > 0 && (
                <span className={clsx(
                  "px-1.5 py-0.5 rounded-full text-[10px] leading-none",
                  activeTab === 'missing' ? "bg-rose-100 dark:bg-rose-500/15 text-rose-600 dark:text-rose-300" : "bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400"
                )}>
                  {missingFiles.length}
                </span>
              )}
            </button>
          </div>

          {/* List Content */}
          <div className="space-y-3">
            {activeTab === 'queue' && (
              <>
                <div className="flex justify-end px-1 mb-1">
                  <button onClick={handleRefresh} className="text-xs font-medium text-slate-400 dark:text-slate-500 flex items-center gap-1 active:text-blue-600 transition-colors">
                    <RefreshCw size={12} /> 刷新状态
                  </button>
                </div>
                {isLoading && (
                  <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800 text-sm text-slate-400 dark:text-slate-500 text-center transition-colors">
                    正在加载归档任务...
                  </div>
                )}
                {!isLoading && error && (
                  <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl shadow-sm border border-rose-100 dark:border-rose-500/20 text-sm text-rose-600 dark:text-rose-300 text-center transition-colors">
                    {error}
                  </div>
                )}
                {!isLoading && !error && displayTasks.length === 0 && (
                  <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800 text-sm text-slate-400 dark:text-slate-500 text-center transition-colors">
                    当前没有归档任务
                  </div>
                )}
                {!isLoading && !error && displayTasks.map(task => (
                  <div key={task.id} className="bg-white dark:bg-slate-900 p-4 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800 flex items-start gap-4 hover:border-slate-200 dark:hover:border-slate-700 transition-colors">
                    <div className={clsx(
                      "p-2.5 rounded-xl shrink-0",
                      task.status === 'running' && 'bg-blue-50 dark:bg-blue-500/10',
                      task.status === 'pending' && 'bg-amber-50 dark:bg-amber-500/10',
                      task.status === 'completed' && 'bg-emerald-50 dark:bg-emerald-500/10',
                      task.status === 'failed' && 'bg-rose-50 dark:bg-rose-500/10'
                    )}>
                      <StatusIcon status={task.status} />
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 leading-snug">
                          {task.title || (task.status === 'pending' ? '排队中...' : task.status === 'running' ? '执行中...' : '未知模型')}
                        </h3>
                      </div>
                      
                      <p className="text-xs text-slate-500 dark:text-slate-400 truncate mb-1.5">{task.url}</p>
                      
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-[10px] text-slate-400 dark:text-slate-500 font-medium">{task.time || task.message || '刚刚更新'}</span>
                        <span className={clsx(
                          "px-2 py-1 rounded-full text-[10px] font-semibold",
                          task.status === 'running' && 'bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-300',
                          task.status === 'pending' && 'bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-300',
                          task.status === 'completed' && 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-300',
                          task.status === 'failed' && 'bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-300',
                        )}>
                          {task.status === 'running' && '归档中'}
                          {task.status === 'pending' && '排队中'}
                          {task.status === 'completed' && '已完成'}
                          {task.status === 'failed' && '失败'}
                        </span>
                        {task.status === 'failed' && (
                          <button className="text-xs text-rose-600 font-semibold bg-rose-50 px-2 py-1 rounded-lg">
                            重试任务
                          </button>
                        )}
                      </div>
                      
                      {task.status === 'running' && (
                        <div className="flex items-center gap-3 mt-3">
                          <div className="flex-1 h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                            <div className="h-full bg-blue-500 rounded-full" style={{ width: `${task.progress || 45}%` }} />
                          </div>
                          <span className="text-[10px] font-bold text-blue-600">{task.progress || 45}%</span>
                        </div>
                      )}

                      {(task.status === 'failed' || task.message) && (task.error || task.message) && (
                        <div className="text-xs text-rose-700 bg-rose-50 p-2.5 rounded-xl mt-3 font-medium border border-rose-100/50">
                          {task.error || task.message}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </>
            )}

            {activeTab === 'missing' && (
              <>
                <div className="flex justify-between items-center px-1 mb-1">
                  <span className="text-xs text-slate-500">共 {missingFiles.length} 个文件存在问题</span>
                  <div className="flex items-center gap-2">
                  <button onClick={handleRefresh} className="text-xs font-medium text-slate-400 dark:text-slate-500 flex items-center gap-1 active:text-blue-600 transition-colors">
                    <RefreshCw size={12} /> 重新扫描
                  </button>
                    <div className="w-px h-3 bg-slate-200"></div>
                    <button 
                      onClick={handleRedownloadAll}
                      className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-1 rounded flex items-center gap-1 hover:bg-blue-100 active:bg-blue-200 transition-colors"
                    >
                      {refreshingId === 'all' ? <Loader2 size={12} className="animate-spin" /> : <RefreshCcw size={12} />} 重新下载所有
                    </button>
                  </div>
                </div>
                {isLoading && (
                  <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800 text-sm text-slate-400 dark:text-slate-500 text-center transition-colors">
                    正在加载缺失文件...
                  </div>
                )}
                {!isLoading && !error && missingFiles.length === 0 && (
                  <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800 text-sm text-slate-400 dark:text-slate-500 text-center transition-colors">
                    当前没有缺失文件
                  </div>
                )}
                {missingFiles.map(file => (
                  <div key={`${file.model_id || file.inst_id || file.base_name || file.url}`} className="bg-white dark:bg-slate-900 p-4 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-800 relative overflow-hidden group transition-colors">
                    <div className="absolute top-0 left-0 w-1 h-full bg-rose-400" />
                    
                    <div className="flex flex-col gap-3">
                      <div>
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="bg-rose-50 text-rose-600 text-[10px] px-2 py-0.5 rounded font-bold border border-rose-100 flex items-center gap-1">
                            <FileWarning size={10} /> 错误信息：{file.error || file.status || '下载失败'}
                          </span>
                        </div>
                        <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 leading-snug">{file.name || file.model_name || file.title || file.base_name || '未知模型'}</h3>
                        <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 font-medium">{file.time || '未知时间'}</p>
                      </div>
                      
                      <div className="flex items-center gap-2 pt-3 border-t border-slate-50 dark:border-slate-800">
                        <button 
                          onClick={() => handleRedownload(file.model_id || file.inst_id || file.base_name || 'single')}
                          disabled={refreshingId === (file.model_id || file.inst_id || file.base_name || 'single')}
                          className="flex-1 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold py-2 rounded-xl text-xs flex items-center justify-center gap-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 active:scale-95 transition-all"
                        >
                          {refreshingId === (file.model_id || file.inst_id || file.base_name || 'single') ? <Loader2 size={14} className="animate-spin text-blue-500" /> : <RefreshCcw size={14} className="text-slate-500" />}
                          {refreshingId === (file.model_id || file.inst_id || file.base_name || 'single') ? '正在重试...' : '重新下载'}
                        </button>
                        <button
                          onClick={() => {
                            if (file.url) {
                              window.open(file.url, '_blank', 'noopener,noreferrer');
                            }
                          }}
                          className="flex-1 bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-300 font-semibold py-2 rounded-xl text-xs flex items-center justify-center gap-1.5 hover:bg-blue-100 dark:hover:bg-blue-500/20 active:scale-95 transition-all"
                        >
                          <ExternalLink size={14} /> 去看看
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
