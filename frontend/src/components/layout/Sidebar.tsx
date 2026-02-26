import { FC, ReactNode } from 'react';
import { Card } from '@/components/common/Card';

interface SidebarProps {
  children: ReactNode;
  queryStats?: ReactNode;
}

export const Sidebar: FC<SidebarProps> = ({ children, queryStats }) => {
  return (
    <div className="h-full flex flex-col p-4 gap-4">
      {/* Main Selector Area */}
      <div className="flex-1 overflow-y-auto space-y-4">
        {children}
      </div>

      {/* Query Stats Panel (if provided) */}
      {queryStats && (
        <div className="border-t border-slate-700 pt-4">
          {queryStats}
        </div>
      )}
    </div>
  );
};
