import { FC } from 'react';
import { useSelectionStore } from '@/store/selectionStore';
import { useQuerySignals } from '@/api/hooks';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { Download, Settings } from 'lucide-react';
import clsx from 'clsx';

interface QueryControlsProps {
  onQueryStart?: () => void;
  onQueryComplete?: (data: any) => void;
  onQueryError?: (error: any) => void;
}

const STRIDE_OPTIONS = [
  { label: 'Every 10th', value: 10 },
  { label: 'Every 100th', value: 100 },
  { label: 'Every 1,000th', value: 1000 },
];

export const QueryControls: FC<QueryControlsProps> = ({
  onQueryStart,
  onQueryComplete,
  onQueryError,
}) => {
  const {
    selectedVehicle,
    selectedSignals,
    timeRange,
    maxPoints,
    setMaxPoints,
    stride,
    setStride,
  } = useSelectionStore();

  const queryMutation = useQuerySignals();

  const canQuery =
    selectedVehicle &&
    selectedSignals.length > 0 &&
    timeRange.start &&
    timeRange.end;

  const handleLoadData = async () => {
    if (!canQuery) return;

    if (onQueryStart) {
      onQueryStart();
    }

    try {
      const result = await queryMutation.mutateAsync({
        vehicleId: selectedVehicle!,
        request: {
          signals: selectedSignals,
          start_time: timeRange.start.toISOString(),
          end_time: timeRange.end.toISOString(),
          max_points: maxPoints,
          ...(stride !== null && { stride }),
        },
      });

      if (onQueryComplete) {
        onQueryComplete(result);
      }
    } catch (error) {
      console.error('Query failed:', error);
      if (onQueryError) {
        onQueryError(error);
      }
    }
  };

  // Max points presets
  const maxPointsPresets = [
    { label: '500', value: 500 },
    { label: '1K', value: 1000 },
    { label: '2K', value: 2000 },
    { label: '5K', value: 5000 },
    { label: '10K', value: 10000 },
  ];

  const btnBase = 'px-2 py-1 text-xs rounded border transition-colors';
  const btnActive = 'bg-primary-500/10 border-primary-500 text-primary-400';
  const btnIdle = 'bg-slate-700/50 border-slate-600 text-slate-400 hover:bg-slate-700';

  return (
    <Card title="Query Settings">

      {/* ── Sampling Mode toggle ─────────────────────────────── */}
      <div className="mb-4">
        <p className="text-xs text-slate-400 mb-2 flex items-center gap-1">
          <Settings className="h-3.5 w-3.5" />
          Sampling Mode
        </p>
        <div className="grid grid-cols-2 gap-1">
          <button
            onClick={() => setStride(null)}
            className={clsx(btnBase, stride === null ? btnActive : btnIdle)}
          >
            LTTB (smart)
          </button>
          <button
            onClick={() => setStride(stride ?? STRIDE_OPTIONS[0].value)}
            className={clsx(btnBase, stride !== null ? btnActive : btnIdle)}
          >
            Stride (every Nth)
          </button>
        </div>
      </div>

      {/* ── LTTB: max-points controls ────────────────────────── */}
      {stride === null && (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-slate-400">Max Points</span>
            <span className="text-xs font-medium text-slate-200">
              {maxPoints.toLocaleString()}
            </span>
          </div>

          <div className="grid grid-cols-5 gap-1 mb-3">
            {maxPointsPresets.map((preset) => (
              <button
                key={preset.value}
                onClick={() => setMaxPoints(preset.value)}
                className={clsx(
                  btnBase,
                  maxPoints === preset.value ? btnActive : btnIdle
                )}
              >
                {preset.label}
              </button>
            ))}
          </div>

          <input
            type="range"
            min="10"
            max="100000"
            step="10"
            value={maxPoints}
            onChange={(e) => setMaxPoints(Number(e.target.value))}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-primary-500"
          />
          <div className="flex justify-between text-xs text-slate-500 mt-1">
            <span>10</span>
            <span>100K</span>
          </div>
        </div>
      )}

      {/* ── Stride: Nth-point selector ───────────────────────── */}
      {stride !== null && (
        <div className="mb-4">
          <p className="text-xs text-slate-400 mb-2">Keep every Nth point</p>
          <div className="grid grid-cols-3 gap-1">
            {STRIDE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setStride(opt.value)}
                className={clsx(
                  btnBase,
                  stride === opt.value ? btnActive : btnIdle
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Info text ────────────────────────────────────────── */}
      <div className="mb-4 p-2 bg-slate-700/30 rounded text-xs text-slate-400">
        {stride === null ? (
          <p>LTTB preserves visual shape with fewer points.</p>
        ) : (
          <p>Stride keeps every {stride.toLocaleString()}th sample uniformly.</p>
        )}
        {selectedSignals.length > 0 && (
          <span className="block mt-1">
            Querying {selectedSignals.length} signal{selectedSignals.length > 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* ── Load Data button ─────────────────────────────────── */}
      <Button
        variant="primary"
        size="lg"
        onClick={handleLoadData}
        disabled={!canQuery}
        loading={queryMutation.isPending}
        className="w-full"
      >
        <Download className="h-4 w-4 mr-2" />
        {queryMutation.isPending ? 'Loading Data...' : 'Load Data'}
      </Button>

      {queryMutation.isError && (
        <div className="mt-3 p-2 bg-red-900/20 border border-red-500/50 rounded text-xs text-red-400">
          {queryMutation.error instanceof Error
            ? queryMutation.error.message
            : 'Failed to load data'}
        </div>
      )}

      {!canQuery && (
        <p className="mt-3 text-xs text-slate-500 text-center">
          {!selectedVehicle
            ? 'Select a vehicle'
            : selectedSignals.length === 0
            ? 'Select at least one signal'
            : 'Ready to load data'}
        </p>
      )}
    </Card>
  );
};
