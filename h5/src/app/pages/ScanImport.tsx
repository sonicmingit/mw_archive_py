import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { ChevronLeft, FolderDown, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { getTools, runScanImport } from '../lib/mobile-api';

export function ScanImport() {
  const navigate = useNavigate();
  const [localPath, setLocalPath] = useState('');
  const [author, setAuthor] = useState('');
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState<null | { total: number, success: number, failed: number }>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let alive = true;
    setIsLoading(true);
    getTools()
      .then((tools) => {
        if (!alive) {
          return;
        }
        setLocalPath(tools.scanImport.watchDirs[0] || '');
      })
      .catch((err: unknown) => {
        if (!alive) {
          return;
        }
        setError(err instanceof Error ? err.message : '加载扫描配置失败');
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

  const handleScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!localPath) return;

    setIsScanning(true);
    setScanResult(null);
    setNotice('');

    try {
      const result = await runScanImport([localPath]);
      const total = Number(result.processed || 0);
      const success = Number(result.imported || 0);
      const failed = Number(result.failed || 0) + Number(result.skipped || 0);
      setScanResult({ total, success, failed });
      if (author.trim()) {
        setNotice('扫描已执行。当前后端未消费“作者”字段，因此该输入仅作为前端保留。');
      } else {
        setNotice('扫描导入已执行完成');
      }
    } catch (err: unknown) {
      setNotice(err instanceof Error ? err.message : '扫描导入失败');
    } finally {
      setIsScanning(false);
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
        <h1 className="text-base font-bold text-slate-800 absolute left-1/2 -translate-x-1/2">扫描导入</h1>
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
            <div className="p-2.5 rounded-xl bg-blue-50 text-blue-600">
              <FolderDown size={24} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-800">从本地文件夹导入</h2>
              <p className="text-xs text-slate-500 mt-0.5">读取真实监控目录并调用后端批量导入</p>
            </div>
          </div>

          <form onSubmit={handleScan} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-2">本地目录路径</label>
              <input
                type="text"
                placeholder="/app/watch"
                value={localPath}
                onChange={(e) => setLocalPath(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow placeholder:text-slate-400"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-2">作者 (可选)</label>
              <input
                type="text"
                placeholder="当前仅作前端备注"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow placeholder:text-slate-400"
              />
            </div>

            <button
              type="submit"
              disabled={!localPath || isScanning || isLoading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-xl flex items-center justify-center gap-2 transition-colors mt-2"
            >
              {isScanning || isLoading ? <Loader2 size={18} className="animate-spin" /> : <FolderDown size={18} />}
              {isLoading ? '加载配置中...' : isScanning ? '扫描中...' : '扫描并导入'}
            </button>
          </form>
        </div>

        {scanResult && (
          <div className="bg-white p-5 rounded-2xl shadow-sm border border-emerald-100 animate-in fade-in slide-in-from-bottom-4 duration-300">
            <div className="flex items-center gap-3 mb-4">
              <CheckCircle2 size={24} className="text-emerald-500" />
              <h3 className="text-sm font-bold text-slate-800">扫描完成</h3>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center divide-x divide-slate-100 border-t border-slate-100 pt-4 mt-2">
              <div>
                <div className="text-xl font-bold text-slate-800">{scanResult.total}</div>
                <div className="text-[10px] text-slate-500 font-medium uppercase mt-1">处理项目</div>
              </div>
              <div>
                <div className="text-xl font-bold text-emerald-600">{scanResult.success}</div>
                <div className="text-[10px] text-slate-500 font-medium uppercase mt-1">成功导入</div>
              </div>
              <div>
                <div className="text-xl font-bold text-rose-500">{scanResult.failed}</div>
                <div className="text-[10px] text-slate-500 font-medium uppercase mt-1">失败 / 跳过</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
