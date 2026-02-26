import { FC } from 'react';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import type { QueryResponse } from '@/api/types';
import { getSignalColor } from '@/utils/colors';
import { Eye, EyeOff } from 'lucide-react';
import clsx from 'clsx';

interface ChartLegendProps {
  data: QueryResponse | null;
  visibleSignals: Set<string>;
  onToggleSignal: (signalName: string) => void;
  onShowAll: () => void;
  onHideAll: () => void;
}

export const ChartLegend: FC<ChartLegendProps> = ({
  data,
  visibleSignals,
  onToggleSignal,
  onShowAll,
  onHideAll,
}) => {
  if (!data || data.signals.length === 0) {
    return null;
  }

  const allVisible = data.signals.every((s) => visibleSignals.has(s.name));
  const noneVisible = data.signals.every((s) => !visibleSignals.has(s.name));

  return (
    <Card title="Chart Legend" className="mt-4">
      {/* Show/Hide All Buttons */}
      <div className="flex gap-2 mb-3">
        <Button
          variant="secondary"
          size="sm"
          onClick={onShowAll}
          disabled={allVisible}
          className="flex-1"
        >
          <Eye className="h-4 w-4 mr-1" />
          Show All
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={onHideAll}
          disabled={noneVisible}
          className="flex-1"
        >
          <EyeOff className="h-4 w-4 mr-1" />
          Hide All
        </Button>
      </div>

      {/* Signal List */}
      <div className="space-y-1 max-h-64 overflow-y-auto">
        {data.signals.map((signal, index) => {
          const isVisible = visibleSignals.has(signal.name);
          const color = getSignalColor(index);

          return (
            <button
              key={signal.name}
              onClick={() => onToggleSignal(signal.name)}
              className={clsx(
                'w-full flex items-center gap-3 px-3 py-2 rounded-md transition-colors text-left',
                isVisible
                  ? 'bg-slate-700 hover:bg-slate-600'
                  : 'bg-slate-800/50 hover:bg-slate-800 opacity-50'
              )}
            >
              {/* Color Indicator */}
              <div
                className="h-3 w-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: color }}
              />

              {/* Signal Info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-200 truncate">
                  {signal.name}
                </p>
                {signal.unit && (
                  <p className="text-xs text-slate-500">{signal.unit}</p>
                )}
              </div>

              {/* Visibility Icon */}
              {isVisible ? (
                <Eye className="h-4 w-4 text-slate-400 flex-shrink-0" />
              ) : (
                <EyeOff className="h-4 w-4 text-slate-600 flex-shrink-0" />
              )}
            </button>
          );
        })}
      </div>

      {/* Summary */}
      <div className="mt-3 pt-3 border-t border-slate-700 text-xs text-slate-400">
        <p>
          Showing {Array.from(visibleSignals).length} of {data.signals.length} signals
        </p>
      </div>
    </Card>
  );
};
