import { FC, useState } from 'react';
import { useSelectionStore } from '@/store/selectionStore';
import { Card } from '@/components/common/Card';
import { TIME_PRESETS, validateTimeRange } from '@/utils/timeRanges';
import { Calendar } from 'lucide-react';
import clsx from 'clsx';

export const TimeRangeSelector: FC = () => {
  const { timeRange, setTimeRange } = useSelectionStore();
  const [customMode, setCustomMode] = useState(false);
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  const handlePresetClick = (presetValue: string) => {
    const preset = TIME_PRESETS.find((p) => p.value === presetValue);
    if (!preset) return;

    const end = new Date();
    const start = new Date(end.getTime() - preset.getDuration());

    setTimeRange({
      start,
      end,
      preset: presetValue,
    });
    setCustomMode(false);
    setValidationError(null);
  };

  const handleCustomApply = () => {
    if (!customStart || !customEnd) {
      setValidationError('Please select both start and end times');
      return;
    }

    const start = new Date(customStart);
    const end = new Date(customEnd);

    const error = validateTimeRange(start, end);
    if (error) {
      setValidationError(error);
      return;
    }

    setTimeRange({ start, end, preset: null });
    setValidationError(null);
  };

  // Format datetime-local input value
  const formatDateTimeLocal = (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  };

  return (
    <Card title="Time Range">
      {/* Preset Buttons */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        {TIME_PRESETS.map((preset) => (
          <button
            key={preset.value}
            onClick={() => handlePresetClick(preset.value)}
            className={clsx(
              'px-3 py-2 text-sm rounded-md border transition-colors',
              timeRange.preset === preset.value
                ? 'bg-primary-500/10 border-primary-500 text-slate-100'
                : 'bg-slate-700/50 border-slate-600 text-slate-300 hover:bg-slate-700 hover:border-slate-500'
            )}
          >
            {preset.label}
          </button>
        ))}
      </div>

      {/* Custom Button */}
      <button
        onClick={() => setCustomMode(!customMode)}
        className={clsx(
          'w-full px-3 py-2 text-sm rounded-md border transition-colors flex items-center justify-center gap-2',
          customMode
            ? 'bg-primary-500/10 border-primary-500 text-slate-100'
            : 'bg-slate-700/50 border-slate-600 text-slate-300 hover:bg-slate-700 hover:border-slate-500'
        )}
      >
        <Calendar className="h-4 w-4" />
        Custom Range
      </button>

      {/* Custom Date Pickers */}
      {customMode && (
        <div className="mt-3 space-y-3 pt-3 border-t border-slate-700">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Start Time</label>
            <input
              type="datetime-local"
              value={customStart || formatDateTimeLocal(timeRange.start)}
              onChange={(e) => setCustomStart(e.target.value)}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-md text-slate-200 text-sm focus:outline-none focus:border-primary-500"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">End Time</label>
            <input
              type="datetime-local"
              value={customEnd || formatDateTimeLocal(timeRange.end)}
              onChange={(e) => setCustomEnd(e.target.value)}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-md text-slate-200 text-sm focus:outline-none focus:border-primary-500"
            />
          </div>

          {validationError && (
            <p className="text-xs text-red-400">{validationError}</p>
          )}

          <button
            onClick={handleCustomApply}
            className="w-full px-3 py-2 bg-primary-500 hover:bg-primary-600 text-white text-sm rounded-md transition-colors"
          >
            Apply Custom Range
          </button>
        </div>
      )}

      {/* Current Selection Display */}
      <div className="mt-3 pt-3 border-t border-slate-700">
        <p className="text-xs text-slate-400">
          Selected: {timeRange.start.toLocaleString()} to {timeRange.end.toLocaleString()}
        </p>
      </div>
    </Card>
  );
};
