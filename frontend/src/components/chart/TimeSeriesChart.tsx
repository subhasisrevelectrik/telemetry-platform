import { FC, useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { QueryResponse } from '@/api/types';
import {
  transformQueryDataToPlotly,
  createPlotlyLayout,
  createPlotlyConfig,
} from '@/utils/chartHelpers';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { TrendingUp } from 'lucide-react';

interface TimeSeriesChartProps {
  data: QueryResponse | null;
  isLoading?: boolean;
  visibleSignals: Set<string>;
  onZoomChange?: (min: number | null, max: number | null) => void;
}

export const TimeSeriesChart: FC<TimeSeriesChartProps> = ({
  data,
  isLoading,
  visibleSignals,
  onZoomChange,
}) => {
  // Transform data for Plotly
  const plotData = useMemo(() => {
    if (!data || data.signals.length === 0) return [];
    return transformQueryDataToPlotly(data, visibleSignals);
  }, [data, visibleSignals]);

  // Create layout configuration
  const layout = useMemo(() => {
    if (!data || data.signals.length === 0) return {};
    return createPlotlyLayout(data);
  }, [data]);

  // Create config options
  const config = useMemo(() => createPlotlyConfig(), []);

  // Handle zoom changes
  const handleRelayout = (event: any) => {
    if (!onZoomChange) return;

    // Plotly relayout event for zoom/pan
    if (event['xaxis.range[0]'] && event['xaxis.range[1]']) {
      const min = new Date(event['xaxis.range[0]']).getTime();
      const max = new Date(event['xaxis.range[1]']).getTime();
      onZoomChange(min, max);
    } else if (event['xaxis.autorange']) {
      // Reset zoom
      onZoomChange(null, null);
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <LoadingSpinner size="lg" text="Loading chart data..." />
      </div>
    );
  }

  // Empty state
  if (!data || data.signals.length === 0) {
    return (
      <EmptyState
        icon={<TrendingUp className="h-16 w-16" />}
        title="No Data Loaded"
        description="Select a vehicle, signals, and time range, then click 'Load Data' to visualize telemetry."
      />
    );
  }

  return (
    <div className="h-full w-full bg-slate-800 rounded-lg p-4">
      <Plot
        data={plotData}
        layout={layout}
        config={config}
        onRelayout={handleRelayout}
        className="w-full h-full"
        useResizeHandler={true}
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  );
};
