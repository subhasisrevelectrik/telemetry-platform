import { FC, ReactNode } from 'react';

interface MainContentProps {
  toolbar?: ReactNode;
  chart?: ReactNode;
  error?: ReactNode;
  empty?: ReactNode;
}

export const MainContent: FC<MainContentProps> = ({ toolbar, chart, error, empty }) => {
  return (
    <div className="h-full flex flex-col bg-slate-900">
      {/* Toolbar */}
      {toolbar && (
        <div className="border-b border-slate-700 bg-slate-800 px-4 py-3">
          {toolbar}
        </div>
      )}

      {/* Chart or Empty State */}
      <div className="flex-1 overflow-hidden p-4">
        {error ? (
          <div className="h-full flex items-start justify-center pt-12">
            {error}
          </div>
        ) : chart ? (
          chart
        ) : (
          <div className="h-full flex items-center justify-center">
            {empty}
          </div>
        )}
      </div>
    </div>
  );
};
