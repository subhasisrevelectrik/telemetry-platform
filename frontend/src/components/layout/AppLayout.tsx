import { FC, ReactNode } from 'react';
import { useSelectionStore } from '@/store/selectionStore';
import clsx from 'clsx';

interface AppLayoutProps {
  topBar: ReactNode;
  sidebar: ReactNode;
  mainContent: ReactNode;
}

export const AppLayout: FC<AppLayoutProps> = ({ topBar, sidebar, mainContent }) => {
  const sidebarCollapsed = useSelectionStore((state) => state.sidebarCollapsed);

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col">
      {/* Top Bar */}
      <header className="border-b border-slate-700 bg-slate-800">
        {topBar}
      </header>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <aside
          className={clsx(
            'border-r border-slate-700 bg-slate-800 transition-all duration-300 overflow-y-auto',
            sidebarCollapsed ? 'w-0' : 'w-full md:w-96'
          )}
        >
          {!sidebarCollapsed && sidebar}
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-hidden">
          {mainContent}
        </main>
      </div>
    </div>
  );
};
