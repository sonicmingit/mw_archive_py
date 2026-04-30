import { useEffect, useState } from 'react';
import {
  Server, Bell, HardDrive, Moon, LogOut, CheckCircle2, Loader2,
  ChevronRight, ChevronLeft, Cookie, FolderSync, FolderOpen,
  Save, AlertCircle, Send
} from 'lucide-react';
import clsx from 'clsx';
import {
  getCookies,
  getSettings,
  getTools,
  runOrganizer,
  saveBatchImportConfig,
  saveCookie,
  saveNotifyConfig,
  saveOrganizerConfig,
  testConnection,
} from '../lib/mobile-api';
import { getApiBaseUrl } from '../lib/api';
import { getStoredTheme, setStoredTheme } from '../lib/theme';

type SubView = 'main' | 'notifications' | 'tasks' | 'cookies';

function joinCookieValues(items: Array<{ value?: string }> | undefined) {
  return (items || []).map((item) => String(item.value || '').trim()).filter(Boolean).join('\n\n');
}

export function Settings() {
  const [activeView, setActiveView] = useState<SubView>('main');
  const [backendUrl, setBackendUrl] = useState(getApiBaseUrl() || (typeof window !== 'undefined' ? window.location.origin : ''));
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<'idle' | 'success' | 'error'>('idle');
  const [pageError, setPageError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [mainNotice, setMainNotice] = useState('');
  const [notificationsNotice, setNotificationsNotice] = useState('');
  const [tasksNotice, setTasksNotice] = useState('');
  const [cookiesNotice, setCookiesNotice] = useState('');

  const [tgEnabled, setTgEnabled] = useState(false);
  const [tgToken, setTgToken] = useState('');
  const [tgChatId, setTgChatId] = useState('');
  const [feishuEnabled, setFeishuEnabled] = useState(false);
  const [feishuWebhook, setFeishuWebhook] = useState('');

  const [testTg, setTestTg] = useState<'idle' | 'testing' | 'success'>('idle');
  const [testFeishu, setTestFeishu] = useState<'idle' | 'testing' | 'success'>('idle');

  const [monitorEnabled, setMonitorEnabled] = useState(false);
  const [importDir, setImportDir] = useState('');
  const [outputDir, setOutputDir] = useState('');
  const [autoOrganize, setAutoOrganize] = useState(false);
  const [isSavingTasks, setIsSavingTasks] = useState(false);
  const [isRunningOrganize, setIsRunningOrganize] = useState(false);

  const [globalCookie, setGlobalCookie] = useState('');
  const [chinaCookie, setChinaCookie] = useState('');
  const [cnCookieCount, setCnCookieCount] = useState(0);
  const [globalCookieCount, setGlobalCookieCount] = useState(0);
  const [cnCookieStatus, setCnCookieStatus] = useState<string[]>([]);
  const [globalCookieStatus, setGlobalCookieStatus] = useState<string[]>([]);
  const [isValidating, setIsValidating] = useState(false);
  const [isSavingCookies, setIsSavingCookies] = useState(false);

  const [isDark, setIsDark] = useState(false);
  const [isSavingNotify, setIsSavingNotify] = useState(false);

  useEffect(() => {
    setIsDark(getStoredTheme() === 'dark');
  }, []);

  useEffect(() => {
    let alive = true;
    setIsLoading(true);
    setPageError('');

    Promise.all([getSettings(), getTools(), getCookies()])
      .then(([settings, tools, cookies]) => {
        if (!alive) {
          return;
        }
        setBackendUrl(getApiBaseUrl() || settings.connection.backendUrl || (typeof window !== 'undefined' ? window.location.origin : ''));
        setTgEnabled(settings.notifications.telegram.enabled);
        setTgToken(settings.notifications.telegram.botToken);
        setTgChatId(settings.notifications.telegram.chatId);
        setFeishuEnabled(settings.notifications.feishu.enabled);
        setFeishuWebhook(settings.notifications.feishu.webhookUrl);

        setMonitorEnabled(tools.scanImport.enabled);
        setImportDir(tools.scanImport.watchDirs[0] || '');
        setOutputDir(tools.organizer.rootDir || '');
        setAutoOrganize((tools.organizer.mode || 'move') === 'move');

        setGlobalCookie(joinCookieValues(cookies.cookie_store.global));
        setChinaCookie(joinCookieValues(cookies.cookie_store.cn));
        setCnCookieCount((cookies.cookie_store.cn || []).length);
        setGlobalCookieCount((cookies.cookie_store.global || []).length);
        setCnCookieStatus((cookies.cookie_store.cn || []).map((item) => String(item.status || '').trim()).filter(Boolean));
        setGlobalCookieStatus((cookies.cookie_store.global || []).map((item) => String(item.status || '').trim()).filter(Boolean));
      })
      .catch((err: unknown) => {
        if (!alive) {
          return;
        }
        setPageError(err instanceof Error ? err.message : '加载设置失败，请稍后重试');
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

  const refreshCookieSummary = async () => {
    const cookies = await getCookies();
    setGlobalCookie(joinCookieValues(cookies.cookie_store.global));
    setChinaCookie(joinCookieValues(cookies.cookie_store.cn));
    setCnCookieCount((cookies.cookie_store.cn || []).length);
    setGlobalCookieCount((cookies.cookie_store.global || []).length);
    setCnCookieStatus((cookies.cookie_store.cn || []).map((item) => String(item.status || '').trim()).filter(Boolean));
    setGlobalCookieStatus((cookies.cookie_store.global || []).map((item) => String(item.status || '').trim()).filter(Boolean));
  };

  const toggleDarkMode = (checked: boolean) => {
    setIsDark(checked);
    setStoredTheme(checked ? 'dark' : 'light');
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult('idle');
    setMainNotice('');
    try {
      await testConnection(backendUrl);
      setTestResult('success');
      setMainNotice('后端连接可用，已更新当前前端请求地址');
      setTimeout(() => setTestResult('idle'), 3000);
    } catch (err: unknown) {
      setTestResult('error');
      setMainNotice(err instanceof Error ? err.message : '连接失败');
    } finally {
      setIsTesting(false);
    }
  };

  const handleTestNotification = async (channel: 'telegram' | 'feishu', setter: (state: 'idle' | 'testing' | 'success') => void) => {
    setter('testing');
    setNotificationsNotice('');
    try {
      await saveNotifyConfig({
        web_base_url: backendUrl,
        telegram: {
          enable_push: tgEnabled,
          bot_token: tgToken,
          chat_id: tgChatId,
        },
        feishu: {
          enable_push: feishuEnabled,
          webhook_url: feishuWebhook,
        },
      });
      const response = await fetch(`${backendUrl.replace(/\/+$/, '')}/api/notify-test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || '测试通知失败');
      }
      setter('success');
      setNotificationsNotice(channel === 'telegram' ? 'Telegram 测试通知已发送' : '飞书测试通知已发送');
      setTimeout(() => setter('idle'), 3000);
    } catch (err: unknown) {
      setter('idle');
      setNotificationsNotice(err instanceof Error ? err.message : '测试通知失败');
    }
  };

  const handleSaveNotifications = async () => {
    setIsSavingNotify(true);
    setNotificationsNotice('');
    try {
      await saveNotifyConfig({
        web_base_url: backendUrl,
        telegram: {
          enable_push: tgEnabled,
          bot_token: tgToken,
          chat_id: tgChatId,
        },
        feishu: {
          enable_push: feishuEnabled,
          webhook_url: feishuWebhook,
        },
      });
      setNotificationsNotice('通知配置已保存');
    } catch (err: unknown) {
      setNotificationsNotice(err instanceof Error ? err.message : '通知配置保存失败');
    } finally {
      setIsSavingNotify(false);
    }
  };

  const handleSaveTasks = async () => {
    setIsSavingTasks(true);
    setTasksNotice('');
    try {
      await saveBatchImportConfig({
        enabled: monitorEnabled,
        watchDirs: importDir ? [importDir] : [],
        processedDirName: '_imported',
        failedDirName: '_failed',
        scanIntervalSeconds: 300,
        notifyOnFinish: true,
        duplicatePolicy: 'skip',
      });
      await saveOrganizerConfig({
        rootDir: outputDir,
        mode: autoOrganize ? 'move' : 'copy',
      });
      setTasksNotice('任务配置已保存');
    } catch (err: unknown) {
      setTasksNotice(err instanceof Error ? err.message : '任务配置保存失败');
    } finally {
      setIsSavingTasks(false);
    }
  };

  const handleRunOrganize = async () => {
    setIsRunningOrganize(true);
    setTasksNotice('');
    try {
      const result = await runOrganizer({
        rootDir: outputDir,
        mode: autoOrganize ? 'move' : 'copy',
      });
      setTasksNotice(`整理任务已执行，处理 ${result.processed || 0} 项，成功 ${result.moved || result.copied || 0} 项`);
    } catch (err: unknown) {
      setTasksNotice(err instanceof Error ? err.message : '整理执行失败');
    } finally {
      setIsRunningOrganize(false);
    }
  };

  const handleValidateCookies = async () => {
    setIsValidating(true);
    setCookiesNotice('');
    try {
      const hasCn = chinaCookie.trim().length > 0;
      const hasGlobal = globalCookie.trim().length > 0;
      if (!hasCn && !hasGlobal) {
        throw new Error('请先粘贴至少一组 Cookie');
      }
      const looksValid = [chinaCookie, globalCookie].filter(Boolean).every((value) => value.includes('=') && value.includes(';'));
      if (!looksValid) {
        throw new Error('Cookie 格式看起来不完整，请确认是浏览器里完整复制的字符串');
      }
      setCookiesNotice('Cookie 文本格式检查通过。当前后端没有独立校验接口，建议直接保存后再执行归档验证。');
      await refreshCookieSummary();
    } catch (err: unknown) {
      setCookiesNotice(err instanceof Error ? err.message : 'Cookie 校验失败');
    } finally {
      setIsValidating(false);
    }
  };

  const handleSaveCookies = async () => {
    setIsSavingCookies(true);
    setCookiesNotice('');
    try {
      if (globalCookie.trim()) {
        await saveCookie('global', globalCookie.trim());
      }
      if (chinaCookie.trim()) {
        await saveCookie('cn', chinaCookie.trim());
      }
      await refreshCookieSummary();
      setCookiesNotice('Cookie 已保存到后端');
    } catch (err: unknown) {
      setCookiesNotice(err instanceof Error ? err.message : 'Cookie 保存失败');
    } finally {
      setIsSavingCookies(false);
    }
  };

  const Section = ({ title, children, className = "" }: { title: string, children: React.ReactNode, className?: string }) => (
    <div className={`mb-6 ${className}`}>
      <h2 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2 px-1 transition-colors">{title}</h2>
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm divide-y divide-slate-100 dark:divide-slate-800/50 transition-colors">
        {children}
      </div>
    </div>
  );

  const Toggle = ({ checked, onChange }: { checked: boolean, onChange: (c: boolean) => void }) => (
    <button
      onClick={() => onChange(!checked)}
      className={`w-12 h-6 rounded-full relative transition-colors duration-300 focus:outline-none ${checked ? 'bg-blue-500 dark:bg-blue-600' : 'bg-slate-200 dark:bg-slate-700'}`}
    >
      <div className={`absolute left-1 top-1 w-4 h-4 bg-white rounded-full shadow-sm transition-transform duration-300 ${checked ? 'translate-x-6' : 'translate-x-0'}`} />
    </button>
  );

  const InputField = ({ label, value, onChange, placeholder = "", type = "text" }: any) => (
    <div className="pt-3 pb-1">
      <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5 transition-colors">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white dark:focus:bg-slate-900 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-600 transition-colors"
      />
    </div>
  );

  const TestButton = ({ state, onClick, label = "发送测试通知" }: { state: 'idle'|'testing'|'success', onClick: () => void, label?: string }) => (
    <button
      onClick={onClick}
      disabled={state === 'testing'}
      className={clsx(
        "w-full mt-4 py-2.5 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors",
        state === 'success'
          ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20"
          : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 active:scale-[0.98]"
      )}
    >
      {state === 'testing' ? <Loader2 size={14} className="animate-spin" /> :
       state === 'success' ? <CheckCircle2 size={14} /> : <Send size={14} />}
      {state === 'testing' ? '发送中...' :
       state === 'success' ? '发送成功' : label}
    </button>
  );

  const Header = ({ title, onBack }: { title: string, onBack?: () => void }) => (
    <header className="px-4 pt-12 pb-4 bg-slate-50 dark:bg-slate-950 sticky top-0 z-10 transition-colors">
      <div className="flex items-center gap-3">
        {onBack && (
          <button onClick={onBack} className="w-10 h-10 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-center text-slate-700 dark:text-slate-300 active:bg-slate-50 dark:active:bg-slate-800 active:scale-95 transition-all shadow-sm shrink-0">
            <ChevronLeft size={20} />
          </button>
        )}
        <h1 className="text-xl font-bold text-slate-900 dark:text-white tracking-tight transition-colors">{title}</h1>
      </div>
    </header>
  );

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-500 dark:text-slate-300">
        <Loader2 size={28} className="animate-spin mb-3" />
        正在加载设置...
      </div>
    );
  }

  if (pageError && activeView === 'main') {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-slate-50 dark:bg-slate-950 p-6 text-center">
        <AlertCircle size={40} className="text-rose-500 mb-3" />
        <p className="text-sm text-rose-600 dark:text-rose-400">{pageError}</p>
      </div>
    );
  }

  if (activeView === 'main') {
    return (
      <div className="flex flex-col min-h-screen bg-slate-50 dark:bg-slate-950 relative pb-safe transition-colors duration-300">
        <Header title="设置" />

        <div className="p-5 pb-10">
          {mainNotice && (
            <div className="mb-5 rounded-2xl border border-blue-100 bg-blue-50 dark:bg-blue-500/10 dark:border-blue-500/20 px-4 py-3 text-sm text-blue-700 dark:text-blue-300">
              {mainNotice}
            </div>
          )}
          <Section title="服务连接">
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-800 dark:text-slate-200 mb-1.5 flex items-center gap-2 transition-colors">
                  <Server size={16} className="text-slate-500 dark:text-slate-400" /> 后端地址
                </label>
                <input
                  type="text"
                  value={backendUrl}
                  onChange={(e) => setBackendUrl(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white dark:focus:bg-slate-900 text-slate-900 dark:text-slate-100 transition-colors"
                />
              </div>
              <button
                onClick={handleTestConnection}
                disabled={isTesting}
                className={clsx(
                  "w-full py-3 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition-colors",
                  testResult === 'success'
                    ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20"
                    : "bg-blue-600 dark:bg-blue-500 text-white hover:bg-blue-700 dark:hover:bg-blue-600 shadow-sm shadow-blue-200 dark:shadow-none active:scale-[0.98]"
                )}
              >
                {isTesting ? <Loader2 size={16} className="animate-spin" /> :
                 testResult === 'success' ? <CheckCircle2 size={16} /> : null}
                {isTesting ? '连接中...' :
                 testResult === 'success' ? '连接成功' : '测试连接'}
              </button>
            </div>
          </Section>

          <Section title="应用设置">
            <div onClick={() => setActiveView('notifications')} className="p-4 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800/50 active:bg-slate-100 dark:active:bg-slate-800 transition-colors cursor-pointer">
              <div className="flex items-center gap-3">
                <div className="bg-blue-100 dark:bg-blue-500/20 p-2.5 rounded-xl"><Bell size={18} className="text-blue-600 dark:text-blue-400" /></div>
                <div>
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-200 transition-colors">通知渠道</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 transition-colors">Telegram、飞书</div>
                </div>
              </div>
              <ChevronRight size={18} className="text-slate-400 dark:text-slate-500" />
            </div>
            <div onClick={() => setActiveView('tasks')} className="p-4 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800/50 active:bg-slate-100 dark:active:bg-slate-800 transition-colors cursor-pointer">
              <div className="flex items-center gap-3">
                <div className="bg-indigo-100 dark:bg-indigo-500/20 p-2.5 rounded-xl"><FolderSync size={18} className="text-indigo-600 dark:text-indigo-400" /></div>
                <div>
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-200 transition-colors">任务设置</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 transition-colors">本地导入与整理目录</div>
                </div>
              </div>
              <ChevronRight size={18} className="text-slate-400 dark:text-slate-500" />
            </div>
            <div onClick={() => setActiveView('cookies')} className="p-4 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800/50 active:bg-slate-100 dark:active:bg-slate-800 transition-colors cursor-pointer">
              <div className="flex items-center gap-3">
                <div className="bg-amber-100 dark:bg-amber-500/20 p-2.5 rounded-xl"><Cookie size={18} className="text-amber-600 dark:text-amber-400" /></div>
                <div>
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-200 transition-colors">Cookie 配置</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 transition-colors">国内 {cnCookieCount} 组 / 国际 {globalCookieCount} 组</div>
                </div>
              </div>
              <ChevronRight size={18} className="text-slate-400 dark:text-slate-500" />
            </div>
          </Section>

          <Section title="其他">
            <div className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="bg-slate-200 dark:bg-slate-800 p-2.5 rounded-xl"><Moon size={18} className="text-slate-600 dark:text-slate-400" /></div>
                <div className="text-sm font-medium text-slate-800 dark:text-slate-200 transition-colors">深色模式</div>
              </div>
              <Toggle checked={isDark} onChange={toggleDarkMode} />
            </div>
          </Section>

          <div className="mt-8">
            <button className="w-full bg-white dark:bg-slate-900 border border-rose-100 dark:border-rose-900/50 text-rose-600 dark:text-rose-400 font-semibold py-3.5 rounded-2xl flex items-center justify-center gap-2 hover:bg-rose-50 dark:hover:bg-rose-900/20 active:scale-[0.98] transition-all shadow-sm">
              <LogOut size={18} /> 清除本地缓存
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (activeView === 'notifications') {
    return (
      <div className="flex flex-col min-h-screen bg-slate-50 dark:bg-slate-950 relative pb-safe transition-colors duration-300">
        <Header title="通知渠道" onBack={() => setActiveView('main')} />
        <div className="p-5 pb-10">
          {notificationsNotice && <div className="mb-5 rounded-2xl border border-blue-100 bg-blue-50 dark:bg-blue-500/10 dark:border-blue-500/20 px-4 py-3 text-sm text-blue-700 dark:text-blue-300">{notificationsNotice}</div>}
          <Section title="Telegram">
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="font-semibold text-slate-800 dark:text-slate-200 text-sm transition-colors">启用 Telegram 推送</div>
                <Toggle checked={tgEnabled} onChange={setTgEnabled} />
              </div>
              {tgEnabled && (
                <div className="mt-3 border-t border-slate-100 dark:border-slate-800/50 pt-1 transition-colors">
                  <div className="space-y-1">
                    <InputField label="Bot Token" value={tgToken} onChange={setTgToken} placeholder="123456:ABC-DEF1234ghIkl..." />
                    <InputField label="Chat ID" value={tgChatId} onChange={setTgChatId} placeholder="-1001234567890" />
                  </div>
                  <TestButton state={testTg} onClick={() => handleTestNotification('telegram', setTestTg)} />
                </div>
              )}
            </div>
          </Section>

          <Section title="飞书 (Feishu)">
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="font-semibold text-slate-800 dark:text-slate-200 text-sm transition-colors">启用飞书机器人</div>
                <Toggle checked={feishuEnabled} onChange={setFeishuEnabled} />
              </div>
              {feishuEnabled && (
                <div className="mt-3 border-t border-slate-100 dark:border-slate-800/50 pt-1 transition-colors">
                  <InputField label="Webhook URL" value={feishuWebhook} onChange={setFeishuWebhook} placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
                  <TestButton state={testFeishu} onClick={() => handleTestNotification('feishu', setTestFeishu)} />
                </div>
              )}
            </div>
          </Section>

          <div className="mt-8 px-1">
            <button
              onClick={handleSaveNotifications}
              disabled={isSavingNotify}
              className="w-full bg-blue-600 dark:bg-blue-500 text-white font-semibold py-3.5 rounded-2xl flex items-center justify-center gap-2 hover:bg-blue-700 dark:hover:bg-blue-600 active:scale-[0.98] transition-all shadow-sm shadow-blue-200 dark:shadow-none"
            >
              {isSavingNotify ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />} 保存配置
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (activeView === 'tasks') {
    return (
      <div className="flex flex-col min-h-screen bg-slate-50 dark:bg-slate-950 relative pb-safe transition-colors duration-300">
        <Header title="任务设置" onBack={() => setActiveView('main')} />
        <div className="p-5 pb-10">
          {tasksNotice && <div className="mb-5 rounded-2xl border border-blue-100 bg-blue-50 dark:bg-blue-500/10 dark:border-blue-500/20 px-4 py-3 text-sm text-blue-700 dark:text-blue-300">{tasksNotice}</div>}
          <Section title="本地目录">
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="font-semibold text-slate-800 dark:text-slate-200 text-sm transition-colors">监控本地导入目录</div>
                <Toggle checked={monitorEnabled} onChange={setMonitorEnabled} />
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-4 leading-relaxed transition-colors">
                开启后，将使用当前监控目录执行批量扫描与导入。
              </p>
              <div className="space-y-4 border-t border-slate-100 dark:border-slate-800/50 pt-4 transition-colors">
                <InputField label={<span className="flex items-center gap-1.5"><FolderOpen size={14} /> 导入目录 (Watch Dir)</span>} value={importDir} onChange={setImportDir} />
                <InputField label={<span className="flex items-center gap-1.5"><HardDrive size={14} /> 整理目录 (Organizer Root)</span>} value={outputDir} onChange={setOutputDir} />
              </div>
            </div>
          </Section>

          <Section title="整理工具">
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="font-semibold text-slate-800 dark:text-slate-200 text-sm transition-colors">整理模式使用 move</div>
                <Toggle checked={autoOrganize} onChange={setAutoOrganize} />
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed mb-4 transition-colors">
                开启时使用 `move`，关闭时使用 `copy`。点击按钮会立即对当前整理目录执行真实整理任务。
              </p>
              <button
                onClick={handleRunOrganize}
                disabled={isRunningOrganize}
                className="w-full bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 font-semibold py-3 rounded-xl flex items-center justify-center gap-2 hover:bg-indigo-100 dark:hover:bg-indigo-500/20 active:scale-[0.98] transition-all border border-indigo-100 dark:border-indigo-500/20"
              >
                {isRunningOrganize ? <Loader2 size={16} className="animate-spin" /> : <FolderSync size={16} />} 立即执行整理
              </button>
            </div>
          </Section>

          <div className="mt-8 px-1">
            <button
              onClick={handleSaveTasks}
              disabled={isSavingTasks}
              className="w-full bg-blue-600 dark:bg-blue-500 text-white font-semibold py-3.5 rounded-2xl flex items-center justify-center gap-2 hover:bg-blue-700 dark:hover:bg-blue-600 active:scale-[0.98] transition-all shadow-sm shadow-blue-200 dark:shadow-none"
            >
              {isSavingTasks ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />} 保存配置
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (activeView === 'cookies') {
    return (
      <div className="flex flex-col min-h-screen bg-slate-50 dark:bg-slate-950 relative pb-safe transition-colors duration-300">
        <Header title="Cookie 配置" onBack={() => setActiveView('main')} />
        <div className="p-5 pb-10">
          {cookiesNotice && <div className="mb-5 rounded-2xl border border-blue-100 bg-blue-50 dark:bg-blue-500/10 dark:border-blue-500/20 px-4 py-3 text-sm text-blue-700 dark:text-blue-300">{cookiesNotice}</div>}
          <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-2xl p-4 mb-6 flex gap-3 transition-colors">
            <AlertCircle size={20} className="text-amber-500 dark:text-amber-400 shrink-0 mt-0.5" />
            <div className="text-xs text-amber-700 dark:text-amber-300/90 leading-relaxed transition-colors">
              当前页面支持直接保存国内 / 国际 Cookie 文本到后端。独立“有效性验证”接口暂未提供，因此这里只做格式检查与数量回读。
            </div>
          </div>

          <Section title={`MakerWorld (Global) · 已保存 ${globalCookieCount} 组`}>
            <div className="p-4 space-y-3">
              <div className="text-[11px] text-slate-500 dark:text-slate-400">状态：{globalCookieStatus.join(' / ') || '暂无'}</div>
              <textarea
                value={globalCookie}
                onChange={(e) => setGlobalCookie(e.target.value)}
                placeholder="在此粘贴 global site 的 cookie 字符串..."
                rows={3}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-600 transition-colors resize-none font-mono"
              />
            </div>
          </Section>

          <Section title={`MakerWorld (China) · 已保存 ${cnCookieCount} 组`}>
            <div className="p-4 space-y-3">
              <div className="text-[11px] text-slate-500 dark:text-slate-400">状态：{cnCookieStatus.join(' / ') || '暂无'}</div>
              <textarea
                value={chinaCookie}
                onChange={(e) => setChinaCookie(e.target.value)}
                placeholder="在此粘贴中国区 site 的 cookie 字符串..."
                rows={3}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-600 transition-colors resize-none font-mono"
              />
            </div>
          </Section>

          <div className="mt-8 px-1 space-y-3">
            <button
              onClick={handleValidateCookies}
              disabled={isValidating}
              className="w-full bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold py-3.5 rounded-2xl flex items-center justify-center gap-2 hover:bg-slate-200 dark:hover:bg-slate-700 active:scale-[0.98] transition-all"
            >
              {isValidating ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle2 size={18} />}
              {isValidating ? '检查中...' : '检查 Cookie 格式'}
            </button>
            <button
              onClick={handleSaveCookies}
              disabled={isSavingCookies}
              className="w-full bg-blue-600 dark:bg-blue-500 text-white font-semibold py-3.5 rounded-2xl flex items-center justify-center gap-2 hover:bg-blue-700 dark:hover:bg-blue-600 active:scale-[0.98] transition-all shadow-sm shadow-blue-200 dark:shadow-none"
            >
              {isSavingCookies ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />} 保存配置
            </button>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
