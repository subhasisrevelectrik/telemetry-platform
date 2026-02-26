import { FC, useEffect } from 'react';
import { useVehicles } from '@/api/hooks';
import { useSelectionStore } from '@/store/selectionStore';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { formatTimestamp } from '@/utils/formatters';
import { Car } from 'lucide-react';
import clsx from 'clsx';

export const VehicleSelector: FC = () => {
  const { data: vehicles, isLoading, error, refetch } = useVehicles();
  const { selectedVehicle, setSelectedVehicle } = useSelectionStore();

  // Auto-select first vehicle if only one exists
  useEffect(() => {
    if (vehicles && vehicles.length === 1 && !selectedVehicle) {
      setSelectedVehicle(vehicles[0].vehicle_id);
    }
  }, [vehicles, selectedVehicle, setSelectedVehicle]);

  if (isLoading) {
    return (
      <Card title="Vehicle">
        <LoadingSpinner size="sm" text="Loading vehicles..." />
      </Card>
    );
  }

  if (error) {
    return (
      <Card title="Vehicle">
        <ErrorBanner
          message={error instanceof Error ? error.message : 'Failed to load vehicles'}
          onRetry={() => refetch()}
        />
      </Card>
    );
  }

  if (!vehicles || vehicles.length === 0) {
    return (
      <Card title="Vehicle">
        <p className="text-sm text-slate-400 text-center py-4">No vehicles found</p>
      </Card>
    );
  }

  return (
    <Card title="Vehicle">
      <div className="space-y-2">
        {vehicles.map((vehicle) => (
          <button
            key={vehicle.vehicle_id}
            onClick={() => setSelectedVehicle(vehicle.vehicle_id)}
            className={clsx(
              'w-full text-left px-3 py-2 rounded-md border transition-colors',
              selectedVehicle === vehicle.vehicle_id
                ? 'bg-primary-500/10 border-primary-500 text-slate-100'
                : 'bg-slate-700/50 border-slate-600 text-slate-300 hover:bg-slate-700 hover:border-slate-500'
            )}
          >
            <div className="flex items-start gap-2">
              <Car className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{vehicle.vehicle_id}</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {formatTimestamp(new Date(vehicle.first_seen).getTime())} - {formatTimestamp(new Date(vehicle.last_seen).getTime())}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {vehicle.frame_count.toLocaleString()} frames
                </p>
              </div>
            </div>
          </button>
        ))}
      </div>
    </Card>
  );
};
