import { Outlet, NavLink, useLocation } from 'react-router';
import { Home, Library, DownloadCloud, Settings } from 'lucide-react';
import clsx from 'clsx';

const LIBRARY_REFRESH_EVENT = 'mw:library-refresh';

export function Layout() {
  const location = useLocation();
  const navItems = [
    {
      to: '/',
      icon: Home,
      label: '总览',
      isActive: (pathname: string) => pathname === '/',
    },
    {
      to: '/library',
      icon: Library,
      label: '模型库',
      isActive: (pathname: string) => pathname === '/library' || pathname.startsWith('/model/'),
    },
    {
      to: '/archive',
      icon: DownloadCloud,
      label: '归档',
      isActive: (pathname: string) => pathname === '/archive',
    },
    {
      to: '/settings',
      icon: Settings,
      label: '设置',
      isActive: (pathname: string) => pathname === '/settings' || pathname === '/scan' || pathname === '/organize',
    },
  ];

  return (
    <div className="bg-slate-900 dark:bg-black h-[100dvh] text-slate-100 flex justify-center w-full font-sans overflow-hidden transition-colors">
      <div className="w-full max-w-md bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex flex-col relative shadow-xl overflow-hidden h-[100dvh] transition-colors">
        {/* Main Content Area */}
        <main className="flex-1 min-h-0 overflow-y-auto overscroll-contain pb-[80px] relative z-0">
          <Outlet />
        </main>

        {/* Bottom Navigation */}
        <nav className="absolute inset-x-0 bottom-0 z-50 border-t border-slate-200/80 dark:border-slate-800/80 bg-white/96 dark:bg-slate-950/96 backdrop-blur-xl shadow-[0_-12px_30px_rgba(15,23,42,0.08)] dark:shadow-[0_-12px_30px_rgba(0,0,0,0.35)] transition-colors">
          <div className="flex justify-around items-center h-[64px] px-2 pb-safe">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className="flex-1 h-full"
              onClick={() => {
                if (item.to === '/library' && item.isActive(location.pathname)) {
                  window.dispatchEvent(new CustomEvent(LIBRARY_REFRESH_EVENT));
                }
              }}
            >
              <div
                className={clsx(
                  'mx-1 my-1.5 flex h-[46px] flex-col items-center justify-center rounded-2xl transition-all duration-200',
                  item.isActive(location.pathname)
                    ? 'bg-blue-50 dark:bg-blue-500/12 text-blue-600 dark:text-blue-400 shadow-[inset_0_0_0_1px_rgba(59,130,246,0.12)] dark:shadow-[inset_0_0_0_1px_rgba(96,165,250,0.18)]'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200',
                )}
              >
                <item.icon size={20} strokeWidth={2.2} />
                <span className="mt-0.5 text-[10px] font-medium">{item.label}</span>
              </div>
            </NavLink>
          ))}
          </div>
        </nav>
      </div>
    </div>
  );
}
