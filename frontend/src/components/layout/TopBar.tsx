import { FC } from 'react';
import { useHealth } from '@/api/hooks';
import { useSelectionStore } from '@/store/selectionStore';
import { Button } from '@/components/common/Button';
import { Menu, X } from 'lucide-react';

export const TopBar: FC = () => {
  const { data: health, isLoading } = useHealth();
  const { sidebarCollapsed, toggleSidebar } = useSelectionStore();

  const appTitle = import.meta.env.VITE_APP_TITLE || 'CAN Telemetry Dashboard';

  return (
    <div className="flex items-center justify-between px-4 py-3">
      {/* Left: Sidebar Toggle + Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleSidebar}
          className="p-2 hover:bg-slate-700 rounded-md transition-colors"
          aria-label={sidebarCollapsed ? 'Show sidebar' : 'Hide sidebar'}
        >
          {sidebarCollapsed ? (
            <Menu className="h-5 w-5 text-slate-400" />
          ) : (
            <X className="h-5 w-5 text-slate-400" />
          )}
        </button>
        <h1 className="text-xl font-semibold text-slate-100">{appTitle}</h1>
      </div>

      {/* Right: Health Status */}
      <div className="flex items-center gap-2">
        {isLoading ? (
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <div className="h-2 w-2 rounded-full bg-slate-500 animate-pulse" />
            <span>Connecting...</span>
          </div>
        ) : health ? (
          <div className="flex items-center gap-2 text-sm">
            <div className="h-2 w-2 rounded-full bg-green-500" />
            <span className="text-slate-300">
              Connected ({health.mode})
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-sm">
            <div className="h-2 w-2 rounded-full bg-red-500" />
            <span className="text-slate-400">Disconnected</span>
          </div>
        )}
      </div>
    </div>
  );
};
