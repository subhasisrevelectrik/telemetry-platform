import { FC } from 'react';
import { Button } from '@/components/common/Button';
import { ZoomIn, ZoomOut, RotateCcw, Download, FileDown } from 'lucide-react';
import type { QueryResponse } from '@/api/types';
import { exportToCSV, downloadCSV } from '@/utils/chartHelpers';

interface ChartToolbarProps {
  data: QueryResponse | null;
  onZoomIn?: () => void;
  onZoomOut?: () => void;
  onResetZoom?: () => void;
  onExportPNG?: () => void;
}

export const ChartToolbar: FC<ChartToolbarProps> = ({
  data,
  onZoomIn,
  onZoomOut,
  onResetZoom,
  onExportPNG,
}) => {
  const handleExportCSV = () => {
    if (!data) return;

    const csv = exportToCSV(data);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `telemetry-export-${timestamp}.csv`;
    downloadCSV(csv, filename);
  };

  const hasData = data && data.signals.length > 0;

  return (
    <div className="flex items-center gap-2">
      {/* Zoom Controls */}
      <div className="flex items-center gap-1 border-r border-slate-600 pr-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={onZoomIn}
          disabled={!hasData}
          aria-label="Zoom in"
        >
          <ZoomIn className="h-4 w-4" />
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={onZoomOut}
          disabled={!hasData}
          aria-label="Zoom out"
        >
          <ZoomOut className="h-4 w-4" />
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={onResetZoom}
          disabled={!hasData}
          aria-label="Reset zoom"
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      </div>

      {/* Export Controls */}
      <div className="flex items-center gap-1">
        <Button
          variant="secondary"
          size="sm"
          onClick={handleExportCSV}
          disabled={!hasData}
          aria-label="Export to CSV"
        >
          <FileDown className="h-4 w-4 mr-1" />
          CSV
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={onExportPNG}
          disabled={!hasData}
          aria-label="Export to PNG"
        >
          <Download className="h-4 w-4 mr-1" />
          PNG
        </Button>
      </div>

      {/* Query Stats */}
      {data?.query_stats && (
        <div className="ml-auto flex items-center gap-4 text-xs text-slate-400 border-l border-slate-600 pl-4">
          <div>
            <span className="text-slate-500">Rows: </span>
            <span className="text-slate-300 font-medium">
              {data.query_stats.rows_scanned.toLocaleString()}
            </span>
          </div>
          <div>
            <span className="text-slate-500">Duration: </span>
            <span className="text-slate-300 font-medium">
              {data.query_stats.duration_ms.toFixed(0)}ms
            </span>
          </div>
          {data.query_stats.downsampled && (
            <div className="text-amber-400">
              <span className="text-slate-500">Downsampled: </span>
              <span className="font-medium">
                {data.query_stats.original_points?.toLocaleString()} → {data.query_stats.downsampled_points?.toLocaleString()}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
