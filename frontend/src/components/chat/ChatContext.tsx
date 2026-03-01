/**
 * Shows the current vehicle/time context in the chat panel header.
 */
import { FC } from 'react';
import { useSelectionStore } from '@/store/selectionStore';

export const ChatContext: FC = () => {
  const selectedVehicle = useSelectionStore((s) => s.selectedVehicle);
  const timeRange = useSelectionStore((s) => s.timeRange);

  const formatDate = (d: Date): string =>
    d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

  return (
    <div className="px-3 py-1.5 bg-slate-900 border-b border-slate-700 text-xs text-slate-400 font-mono flex items-center gap-3">
      <span>
        <span className="text-slate-500">vehicle: </span>
        <span className={selectedVehicle ? 'text-cyan-400' : 'text-slate-600'}>
          {selectedVehicle ?? 'none'}
        </span>
      </span>
      <span className="text-slate-700">|</span>
      <span>
        <span className="text-slate-500">range: </span>
        <span className="text-slate-400">
          {formatDate(timeRange.start)} – {formatDate(timeRange.end)}
        </span>
      </span>
    </div>
  );
};
