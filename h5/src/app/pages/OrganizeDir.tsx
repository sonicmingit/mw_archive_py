import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { ChevronLeft, FolderSync, Loader2, HardDrive, CheckCircle2, AlertCircle } from 'lucide-react';
import clsx from 'clsx';
import { getTools, runOrganizer } from '../lib/mobile-api';

export function OrganizeDir() {
  const navigate = useNavigate();
  const [modelDir, setModelDir] = useState('');
  const [isOrganizing, setIsOrganizing] = useState(false);
  const [organizeResult, setOrganizeResult] = useState<null | { processed: number, moved: number }>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [mode, setMode] = useState<'move' | 'copy'>('move');

  useEffect(() => {
    let alive = true;
    setIsLoading(true);
    getTools()
      .then((tools) => {
        if (!alive) {
          return;
        }
        setModelDir(tools.organizer.rootDir || '');
        setMode((tools.organizer.mode || 'move') === 'copy' ? 'copy' : 'move');
      })
      .catch((err: unknown) => {
        if (!alive) {
          return;
        }
        setError(err instanceof Error ? err.message : '加载整理配置失败');
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

  const handleOrganize = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!modelDir) return;

    setIsOrganizing(true);
    setOrganizeResult(null);
    setNotice('');

    try {
      const result = await runOrganizer({ rootDir: modelDir, mode });
      setOrganizeResult({
        processed: Number(result.processed || 0),
        moved: Number(result.moved || result.copied || 0),
      });
      setNotice(`真实整理任务已执行，模式为 ${mode}`);
    } catch (err: unknown) {
      setNotice(err instanceof Error ? err.message : '整理目录失败');
    } finally {
      setIsOrganizing(false);
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 relative pb-10">
      <header className="fixed top-0 left-0 right-0 max-w-md mx-auto w-full z-50 px-4 pt-12 pb-3 bg-white/80 backdrop-blur-md border-b border-slate-200 flex items-center justify-between pointer-events-none">
        <button
          onClick={() => navigate(-1)}
          className="w-10 h-10 -ml-2 rounded-full flex items-center justify-center text-slate-700 pointer-events-auto transition-transform active:scale-90"
        >
          <ChevronLeft size={24} />
        </button>
        <h1 className="text-base font-bold text-slate-800 absolute left-1/2 -translate-x-1/2">整理目录</h1>
        <div className="w-10 h-10"></div>
      </header>

      <div className="pt-24 px-5 space-y-6">
        {notice && (
          <div className="bg-blue-50 text-blue-700 text-sm font-medium px-4 py-3 rounded-2xl border border-blue-100">
            {notice}
          </div>
        )}
        {error && (
          <div className="bg-rose-50 text-rose-600 text-sm font-medium px-4 py-3 rounded-2xl border border-rose-100 flex items-center gap-2">
            <AlertCircle size={16} /> {error}
          </div>
        )}
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100">
          <div className="flex items-center gap-3 mb-5">
            <div className="p-2.5 rounded-xl bg-indigo-50 text-indigo-600">
              <FolderSync size={24} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-800">整理本地 3MF 文件</h2>
              <p className="text-xs text-slate-500 mt-0.5">使用真实整理目录配置并调用后端整理任务</p>
            </div>
          </div>

          <form onSubmit={handleOrganize} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-2">模型存放目录</label>
              <div className="relative flex items-center">
                <HardDrive className="absolute left-3 text-slate-400" size={18} />
                <input
                  type="text"
                  placeholder="/app/organize"
                  value={modelDir}
                  onChange={(e) => setModelDir(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl py-3 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-shadow placeholder:text-slate-400"
                />
              </div>
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setMode('move')}
                className={clsx('flex-1 rounded-xl py-2.5 text-sm font-semibold border transition-colors', mode === 'move' ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-slate-50 text-slate-700 border-slate-200')}
              >
                move
              </button>
              <button
                type="button"
                onClick={() => setMode('copy')}
                className={clsx('flex-1 rounded-xl py-2.5 text-sm font-semibold border transition-colors', mode === 'copy' ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-slate-50 text-slate-700 border-slate-200')}
              >
                copy
              </button>
            </div>

            <button
              type="submit"
              disabled={!modelDir || isOrganizing || isLoading}
              className={clsx(
                "w-full text-white font-semibold py-3 rounded-xl flex items-center justify-center gap-2 transition-colors mt-2",
                !modelDir || isOrganizing || isLoading
                  ? "bg-indigo-300 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-700"
              )}
            >
              {isOrganizing || isLoading ? <Loader2 size={18} className="animate-spin" /> : <FolderSync size={18} />}
              {isLoading ? '加载配置中...' : isOrganizing ? '整理中...' : '开始整理'}
            </button>
          </form>
        </div>

        <div className="bg-blue-50 border border-blue-100 rounded-2xl p-4 flex gap-3">
          <div className="mt-0.5 text-blue-500"><FolderSync size={18} /></div>
          <div>
            <h4 className="text-sm font-semibold text-slate-800">说明</h4>
            <p className="text-xs text-slate-600 leading-relaxed mt-1">
              当前页面会把输入目录和模式直接提交给后端 `/api/local-3mf-organizer/run`，执行真实整理任务。
            </p>
          </div>
        </div>

        {organizeResult && (
          <div className="bg-white p-5 rounded-2xl shadow-sm border border-emerald-100 animate-in fade-in slide-in-from-bottom-4 duration-300">
            <div className="flex items-center gap-3 mb-4">
              <CheckCircle2 size={24} className="text-emerald-500" />
              <h3 className="text-sm font-bold text-slate-800">整理完成</h3>
            </div>
            <div className="grid grid-cols-2 gap-3 text-center divide-x divide-slate-100 border-t border-slate-100 pt-4 mt-2">
              <div>
                <div className="text-xl font-bold text-slate-800">{organizeResult.processed}</div>
                <div className="text-[10px] text-slate-500 font-medium uppercase mt-1">处理文件</div>
              </div>
              <div>
                <div className="text-xl font-bold text-emerald-600">{organizeResult.moved}</div>
                <div className="text-[10px] text-slate-500 font-medium uppercase mt-1">成功处理</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
