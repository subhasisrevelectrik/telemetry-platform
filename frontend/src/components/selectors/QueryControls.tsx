import { FC } from 'react';
import { useSelectionStore } from '@/store/selectionStore';
import { useQuerySignals } from '@/api/hooks';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { Download } from 'lucide-react';

interface QueryControlsProps {
  onQueryStart?: () => void;
  onQueryComplete?: (data: any) => void;
  onQueryError?: (error: any) => void;
}

export const QueryControls: FC<QueryControlsProps> = ({
  onQueryStart,
  onQueryComplete,
  onQueryError,
}) => {
  const { selectedVehicle, selectedSignals, timeRange } = useSelectionStore();

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

  return (
    <Card title="Load Data">
      {selectedSignals.length > 0 && (
        <p className="mb-3 text-xs text-slate-400">
          {selectedSignals.length} signal{selectedSignals.length !== 1 ? 's' : ''} selected
          {' — '}data will be downsampled automatically to fit the view.
        </p>
      )}

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
