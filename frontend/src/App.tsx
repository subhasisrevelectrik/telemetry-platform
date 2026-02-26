import { useState } from 'react';
import { AppLayout } from '@/components/layout/AppLayout';
import { TopBar } from '@/components/layout/TopBar';
import { Sidebar } from '@/components/layout/Sidebar';
import { MainContent } from '@/components/layout/MainContent';
import { VehicleSelector } from '@/components/selectors/VehicleSelector';
import { TimeRangeSelector } from '@/components/selectors/TimeRangeSelector';
import { SignalSelector } from '@/components/selectors/SignalSelector';
import { QueryControls } from '@/components/selectors/QueryControls';
import { TimeSeriesChart } from '@/components/chart/TimeSeriesChart';
import { ChartToolbar } from '@/components/chart/ChartToolbar';
import { ChartLegend } from '@/components/chart/ChartLegend';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { useChartStore } from '@/store/chartStore';

function App() {
  const {
    queryData,
    setQueryData,
    visibleSignals,
    toggleSignal,
    showAllSignals,
    hideAllSignals,
    zoomRange,
    setZoomRange,
    resetZoom,
  } = useChartStore();

  const [isLoading, setIsLoading] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);

  const handleQueryStart = () => {
    setIsLoading(true);
    setQueryError(null);
  };

  const handleQueryComplete = (data: any) => {
    setQueryData(data);
    setIsLoading(false);
    setQueryError(null);
  };

  const handleQueryError = (error: any) => {
    setIsLoading(false);
    setQueryError(error?.message || 'Failed to load data');
  };

  const handleZoomIn = () => {
    // Zoom in by 50%
    if (zoomRange.min !== null && zoomRange.max !== null) {
      const range = zoomRange.max - zoomRange.min;
      const newRange = range * 0.5;
      const center = (zoomRange.min + zoomRange.max) / 2;
      setZoomRange(center - newRange / 2, center + newRange / 2);
    }
  };

  const handleZoomOut = () => {
    // Zoom out by 50%
    if (zoomRange.min !== null && zoomRange.max !== null) {
      const range = zoomRange.max - zoomRange.min;
      const newRange = range * 1.5;
      const center = (zoomRange.min + zoomRange.max) / 2;
      setZoomRange(center - newRange / 2, center + newRange / 2);
    }
  };

  const handleResetZoom = () => {
    resetZoom();
  };

  const handleExportPNG = () => {
    // TODO: Implement PNG export using canvas
    console.log('PNG export not yet implemented');
  };

  return (
    <AppLayout
      topBar={<TopBar />}
      sidebar={
        <Sidebar>
          <VehicleSelector />
          <TimeRangeSelector />
          <SignalSelector />
          <QueryControls
            onQueryStart={handleQueryStart}
            onQueryComplete={handleQueryComplete}
            onQueryError={handleQueryError}
          />
        </Sidebar>
      }
      mainContent={
        <MainContent
          toolbar={
            <ChartToolbar
              data={queryData}
              onZoomIn={handleZoomIn}
              onZoomOut={handleZoomOut}
              onResetZoom={handleResetZoom}
              onExportPNG={handleExportPNG}
            />
          }
          chart={
            <div className="h-full flex flex-col">
              <TimeSeriesChart
                data={queryData}
                isLoading={isLoading}
                visibleSignals={visibleSignals}
                onZoomChange={setZoomRange}
              />
              <ChartLegend
                data={queryData}
                visibleSignals={visibleSignals}
                onToggleSignal={toggleSignal}
                onShowAll={showAllSignals}
                onHideAll={hideAllSignals}
              />
            </div>
          }
          error={
            queryError ? (
              <ErrorBanner
                message={queryError}
                onDismiss={() => setQueryError(null)}
              />
            ) : undefined
          }
        />
      }
    />
  );
}

export default App;
