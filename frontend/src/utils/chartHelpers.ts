import type { Data, Layout, Config } from 'plotly.js';
import type { QueryResponse } from '@/api/types';
import { getSignalColor } from './colors';

/**
 * Detect significant time gaps between consecutive data points and insert
 * null y-values at gap midpoints so Plotly draws a visual break in the line.
 *
 * A "significant" gap is defined as > thresholdMultiplier × the median
 * inter-sample interval of the dataset.  This adapts automatically to any
 * sampling rate without hard-coded time thresholds.
 */
function insertGapNulls(
  tMs: number[],
  vals: number[],
  thresholdMultiplier = 5
): { tMs: number[]; vals: (number | null)[] } {
  if (tMs.length < 3) {
    return { tMs, vals };
  }

  // Compute all consecutive intervals, then find the median
  const intervals: number[] = [];
  for (let i = 1; i < tMs.length; i++) {
    intervals.push(tMs[i] - tMs[i - 1]);
  }
  const sorted = [...intervals].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const threshold = median * thresholdMultiplier;

  // Build output arrays, inserting a null at the midpoint of each large gap
  const outT: number[] = [tMs[0]];
  const outV: (number | null)[] = [vals[0]];
  for (let i = 1; i < tMs.length; i++) {
    if (tMs[i] - tMs[i - 1] > threshold) {
      outT.push((tMs[i - 1] + tMs[i]) / 2);
      outV.push(null);
    }
    outT.push(tMs[i]);
    outV.push(vals[i]);
  }

  return { tMs: outT, vals: outV };
}

/**
 * Transform QueryResponse data into Plotly format
 * Plotly expects array of traces: [{x: [], y: [], type: 'scatter', ...}]
 */
export function transformQueryDataToPlotly(
  queryResponse: QueryResponse,
  visibleSignals: Set<string>
): Data[] {
  if (!queryResponse.signals || queryResponse.signals.length === 0) {
    return [];
  }

  const traces: Data[] = [];
  const unitGroups = groupSignalsByUnit(queryResponse.signals);
  const yaxisAssignments = assignYAxes(queryResponse.signals, unitGroups);

  queryResponse.signals.forEach((signal, index) => {
    const signalKey = signal.name;
    const isVisible = visibleSignals.has(signalKey);

    // Validate and prepare data
    const validData = signal.data.filter(
      (point) =>
        typeof point.t === 'number' &&
        isFinite(point.t) &&
        point.t > 0 &&
        typeof point.v === 'number' &&
        isFinite(point.v)
    );

    if (validData.length === 0) {
      console.warn(`No valid data for signal: ${signal.name}`);
      return;
    }

    // Sort by timestamp before gap detection
    const sortedData = [...validData].sort((a, b) => a.t - b.t);

    // Detect significant time gaps and insert nulls so Plotly draws breaks
    const { tMs: gappedTMs, vals: gappedVals } = insertGapNulls(
      sortedData.map((p) => p.t),
      sortedData.map((p) => p.v)
    );

    // Convert timestamps to local-time strings.
    // Plotly's type:'date' axis renders strings as-is (no tz conversion),
    // so we shift each UTC ms value by the browser's UTC offset to get
    // the correct local clock time on the axis.
    const tzOffsetMs = new Date().getTimezoneOffset() * 60 * 1000;
    const timestamps = gappedTMs.map((t) =>
      new Date(t - tzOffsetMs).toISOString().slice(0, 23)
    );

    const trace: Data = {
      x: timestamps,
      y: gappedVals,
      connectgaps: false,
      type: 'scatter',
      mode: 'lines',
      name: `${signal.name} (${signal.unit || ''})`,
      line: {
        color: getSignalColor(index),
        width: 2,
      },
      visible: isVisible ? true : 'legendonly',
      yaxis: yaxisAssignments[index],
      hovertemplate:
        '<b>%{fullData.name}</b><br>' +
        'Time: %{x}<br>' +
        'Value: %{y:.3f}<br>' +
        '<extra></extra>',
    };

    traces.push(trace);
  });

  return traces;
}

/**
 * Group signals by unit to determine Y-axes
 */
export function groupSignalsByUnit(
  signals: QueryResponse['signals']
): Map<string, number[]> {
  const unitGroups = new Map<string, number[]>();

  signals.forEach((signal, index) => {
    const unit = signal.unit || 'no_unit';
    if (!unitGroups.has(unit)) {
      unitGroups.set(unit, []);
    }
    unitGroups.get(unit)!.push(index);
  });

  return unitGroups;
}

/**
 * Assign Y-axis to each signal (y, y2, y3)
 * Plotly supports multiple Y-axes on left and right sides
 */
export function assignYAxes(
  signals: QueryResponse['signals'],
  unitGroups: Map<string, number[]>
): string[] {
  const units = Array.from(unitGroups.keys()).slice(0, 3); // Max 3 Y-axes
  const assignments: string[] = [];

  signals.forEach((signal) => {
    const unit = signal.unit || 'no_unit';
    const unitIndex = units.indexOf(unit);

    if (unitIndex === -1) {
      // If unit not in top 3, assign to first axis
      assignments.push('y');
    } else if (unitIndex === 0) {
      assignments.push('y');
    } else if (unitIndex === 1) {
      assignments.push('y2');
    } else {
      assignments.push('y3');
    }
  });

  return assignments;
}

/**
 * Create Plotly layout configuration with multi-Y-axis support
 */
export function createPlotlyLayout(
  queryResponse: QueryResponse,
  width?: number,
  height?: number
): Partial<Layout> {
  const unitGroups = groupSignalsByUnit(queryResponse.signals);
  const units = Array.from(unitGroups.keys()).slice(0, 3);

  const layout: Partial<Layout> & Record<string, any> = {
    autosize: true,
    width: width,
    height: height,
    margin: { l: 60, r: 60, t: 40, b: 60 },
    paper_bgcolor: '#1e293b', // slate-800
    plot_bgcolor: '#0f172a', // slate-900
    font: {
      color: '#cbd5e1', // slate-300
      family: 'system-ui, -apple-system, sans-serif',
      size: 12,
    },
    hovermode: 'x unified',
    showlegend: true,
    legend: {
      orientation: 'h',
      yanchor: 'bottom',
      y: -0.2,
      xanchor: 'center',
      x: 0.5,
      bgcolor: 'rgba(30, 41, 59, 0.8)',
      bordercolor: '#475569',
      borderwidth: 1,
    },
    xaxis: {
      title: 'Time',
      type: 'date',
      gridcolor: '#334155',
      showgrid: true,
      zeroline: false,
      color: '#cbd5e1',
      rangeslider: {
        visible: true,
        bgcolor: '#1e293b',
        bordercolor: '#475569',
        borderwidth: 1,
      },
    },
  };

  // Configure Y-axes based on unique units
  units.forEach((unit, index) => {
    const axisKey = index === 0 ? 'yaxis' : `yaxis${index + 1}`;
    const side = index % 2 === 0 ? 'left' : 'right';

    layout[axisKey] = {
      title: unit === 'no_unit' ? 'Value' : unit,
      side: side,
      gridcolor: index === 0 ? '#334155' : 'transparent',
      showgrid: index === 0,
      zeroline: false,
      color: '#cbd5e1',
      overlaying: index > 0 ? 'y' : undefined,
      anchor: index > 1 ? 'free' : undefined,
      position: index === 2 ? 0.05 : undefined, // Position 3rd axis
    };
  });

  return layout;
}

/**
 * Create Plotly config options
 */
export function createPlotlyConfig(): Partial<Config> {
  return {
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'],
    toImageButtonOptions: {
      format: 'png',
      filename: 'telemetry_chart',
      height: 800,
      width: 1200,
      scale: 2,
    },
    responsive: true,
  };
}

/**
 * Export chart data to CSV
 */
export function exportToCSV(queryResponse: QueryResponse): string {
  const lines: string[] = [];

  // Header
  const headers = [
    'timestamp',
    ...queryResponse.signals.map((s) => `${s.name} (${s.unit || ''})`),
  ];
  lines.push(headers.join(','));

  // Get all unique timestamps
  const timestampSet = new Set<number>();
  queryResponse.signals.forEach((signal) => {
    signal.data.forEach((point) => timestampSet.add(point.t));
  });
  const timestamps = Array.from(timestampSet).sort((a, b) => a - b);

  // Data rows
  timestamps.forEach((timestamp) => {
    const row = [new Date(timestamp).toISOString()];
    queryResponse.signals.forEach((signal) => {
      const point = signal.data.find((p) => p.t === timestamp);
      row.push(point ? String(point.v) : '');
    });
    lines.push(row.join(','));
  });

  return lines.join('\n');
}

/**
 * Download CSV file
 */
export function downloadCSV(csv: string, filename: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);

  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  link.style.visibility = 'hidden';

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  URL.revokeObjectURL(url);
}
