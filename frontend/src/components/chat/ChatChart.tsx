/**
 * Inline Plotly.js chart rendered from a chat AI response.
 *
 * Uses the same dark-theme color palette as the main dashboard TimeSeriesChart.
 */
import { FC, useMemo, useState } from 'react';
import Plot from 'react-plotly.js';
import type { Data, Layout } from 'plotly.js';
import type { ChatChart as ChatChartType } from './chatTypes';
import { getSignalColor } from '@/utils/colors';
import { useChatStore } from './useChatStore';
import { LayoutDashboard, Maximize2, X } from 'lucide-react';

interface ChatChartProps {
  chart: ChatChartType;
}

function buildTraces(chart: ChatChartType): Data[] {
  const entries = Object.entries(chart.data);
  const unitSet = new Set(entries.map(([, sd]) => sd.unit || ''));
  const units = Array.from(unitSet).slice(0, 3);

  const tzOffsetMs = new Date().getTimezoneOffset() * 60 * 1000;

  return entries.map(([key, signalData], idx) => {
    const unit = signalData.unit || '';
    const unitIdx = units.indexOf(unit);
    const yaxis = unitIdx <= 0 ? 'y' : unitIdx === 1 ? 'y2' : 'y3';

    const x = signalData.timestamps.map((ts) =>
      new Date(new Date(ts).getTime() - tzOffsetMs).toISOString().slice(0, 23)
    );
    const y: (number | null)[] = signalData.values;

    return {
      x,
      y,
      connectgaps: false,
      type: 'scatter',
      mode: 'lines',
      name: key.split('.').slice(1).join('.') || key,
      line: { color: getSignalColor(idx), width: 1.5 },
      yaxis,
      hovertemplate: '<b>%{fullData.name}</b><br>Time: %{x}<br>Value: %{y:.3f}<extra></extra>',
    } as Data;
  });
}

function buildLayout(chart: ChatChartType, height: number): Partial<Layout> {
  const entries = Object.entries(chart.data);
  const unitSet = new Set(entries.map(([, sd]) => sd.unit || ''));
  const units = Array.from(unitSet).slice(0, 3);

  const layout: Partial<Layout> & Record<string, unknown> = {
    title: { text: chart.title, font: { color: '#cbd5e1', size: 12 }, x: 0.02 },
    autosize: true,
    height,
    margin: { l: 48, r: units.length > 1 ? 48 : 12, t: 28, b: 40 },
    paper_bgcolor: '#1e293b',
    plot_bgcolor: '#0f172a',
    font: { color: '#94a3b8', size: 10, family: 'system-ui, sans-serif' },
    hovermode: 'x unified',
    showlegend: true,
    legend: {
      orientation: 'h',
      yanchor: 'bottom',
      y: -0.22,
      xanchor: 'center',
      x: 0.5,
      bgcolor: 'rgba(30,41,59,0.8)',
      bordercolor: '#475569',
      borderwidth: 1,
      font: { size: 9 },
    },
    xaxis: {
      type: 'date',
      gridcolor: '#334155',
      showgrid: true,
      zeroline: false,
      color: '#94a3b8',
      tickfont: { size: 9 },
    },
    shapes: chart.threshold_lines.map((tl) => ({
      type: 'line',
      xref: 'paper',
      x0: 0,
      x1: 1,
      yref: 'y',
      y0: tl.value,
      y1: tl.value,
      line: { color: tl.color || '#f59e0b', width: 1, dash: 'dash' },
    })),
  };

  units.forEach((unit, i) => {
    const key = i === 0 ? 'yaxis' : `yaxis${i + 1}`;
    layout[key] = {
      title: { text: unit || 'Value', font: { size: 9, color: '#94a3b8' } },
      side: i % 2 === 0 ? 'left' : 'right',
      gridcolor: i === 0 ? '#334155' : 'transparent',
      showgrid: i === 0,
      zeroline: false,
      color: '#94a3b8',
      overlaying: i > 0 ? 'y' : undefined,
      tickfont: { size: 9 },
    };
  });

  return layout;
}

export const ChatChart: FC<ChatChartProps> = ({ chart }) => {
  const [expanded, setExpanded] = useState(false);
  const addChartToDashboard = useChatStore((s) => s.addChartToDashboard);

  const traces = useMemo(() => buildTraces(chart), [chart]);
  const compactLayout = useMemo(() => buildLayout(chart, 220), [chart]);
  const expandedLayout = useMemo(() => buildLayout(chart, 500), [chart]);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const config: any = {
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'toImage'],
    responsive: true,
  };

  if (!traces.length) {
    return (
      <div className="mt-2 p-3 rounded bg-slate-800 border border-slate-700 text-slate-400 text-xs">
        No data available for this chart.
      </div>
    );
  }

  return (
    <>
      {/* Compact inline chart */}
      <div className="mt-2 rounded-lg border border-slate-700 overflow-hidden bg-slate-800">
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-700 bg-slate-800/80">
          <span className="text-xs text-slate-400 font-mono truncate max-w-[200px]">
            {chart.title}
          </span>
          <div className="flex gap-2 ml-2 flex-shrink-0">
            <button
              onClick={() => addChartToDashboard(chart)}
              title="Add to main dashboard"
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-cyan-400 transition-colors"
            >
              <LayoutDashboard className="h-3 w-3" />
              <span className="hidden sm:inline">Dashboard</span>
            </button>
            <button
              onClick={() => setExpanded(true)}
              title="Expand chart"
              className="text-slate-400 hover:text-cyan-400 transition-colors"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
        <Plot
          data={traces}
          layout={compactLayout}
          config={config}
          style={{ width: '100%' }}
          useResizeHandler
        />
      </div>

      {/* Expanded modal */}
      {expanded && (
        <div
          className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
          onClick={() => setExpanded(false)}
        >
          <div
            className="bg-slate-900 rounded-xl border border-slate-600 w-full max-w-4xl shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
              <h3 className="text-sm font-semibold text-slate-200">{chart.title}</h3>
              <button
                onClick={() => setExpanded(false)}
                className="text-slate-400 hover:text-slate-200 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-4">
              <Plot
                data={traces}
                layout={expandedLayout}
                config={{ ...config, displayModeBar: true }}
                style={{ width: '100%' }}
                useResizeHandler
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
};
