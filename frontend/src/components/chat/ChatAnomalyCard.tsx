/**
 * Renders an anomaly detection result card with a sparkline.
 */
import { FC, useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { AnomalyResult } from './chatTypes';
import { AlertTriangle } from 'lucide-react';

interface ChatAnomalyCardProps {
  anomaly: AnomalyResult;
}

function exportAnomalyCSV(anomaly: AnomalyResult): void {
  const lines = ['timestamp,value,reason,severity'];
  for (const a of anomaly.anomalies) {
    lines.push(`${a.timestamp},${a.value},"${a.reason}",${a.severity}`);
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `anomalies_${anomaly.signal_name}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export const ChatAnomalyCard: FC<ChatAnomalyCardProps> = ({ anomaly }) => {
  const criticalCount = anomaly.anomalies.filter((a) => a.severity === 'critical').length;
  const warningCount = anomaly.anomalies.filter((a) => a.severity === 'warning').length;

  // Build sparkline data
  const anomalyTs = useMemo(
    () => new Set(anomaly.anomalies.map((a) => a.timestamp)),
    [anomaly.anomalies]
  );

  const sparkData = useMemo(() => {
    if (!anomaly.anomalies.length) return { x: [], y: [], colors: [] };
    const sorted = [...anomaly.anomalies].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
    return {
      x: sorted.map((a) => a.timestamp),
      y: sorted.map((a) => a.value),
      colors: sorted.map((a) =>
        a.severity === 'critical' ? '#ef4444' : '#f59e0b'
      ),
    };
  }, [anomaly.anomalies]);

  const formatVal = (v: number): string =>
    Math.abs(v) >= 1000 ? v.toFixed(0) : v.toPrecision(4);

  return (
    <div className="mt-2 rounded-lg border border-slate-600 bg-slate-800/60 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 bg-slate-800">
        <AlertTriangle className="h-4 w-4 text-amber-400 flex-shrink-0" />
        <span className="text-sm font-semibold text-slate-200 font-mono">
          {anomaly.signal_name}
        </span>
        {anomaly.message_name && (
          <span className="text-xs text-slate-500 font-mono">
            ({anomaly.message_name})
          </span>
        )}
        <div className="ml-auto flex gap-2 text-xs">
          {criticalCount > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-red-900/60 text-red-400">
              {criticalCount} critical
            </span>
          )}
          {warningCount > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-amber-900/60 text-amber-400">
              {warningCount} warning
            </span>
          )}
        </div>
      </div>

      {/* Sparkline — only if anomalies have timestamps */}
      {sparkData.x.length > 0 && (
        <div className="px-2 pt-2">
          <Plot
            data={[
              {
                x: sparkData.x,
                y: sparkData.y,
                type: 'scatter',
                mode: 'markers',
                marker: { color: sparkData.colors, size: 6 },
              },
            ]}
            layout={{
              height: 60,
              margin: { l: 30, r: 8, t: 4, b: 20 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              xaxis: { showticklabels: false, showgrid: false, zeroline: false },
              yaxis: { showgrid: false, zeroline: false, color: '#94a3b8', tickfont: { size: 9 } },
              showlegend: false,
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%' }}
            useResizeHandler
          />
        </div>
      )}

      {/* Anomaly list */}
      {anomaly.anomalies.length > 0 && (
        <div className="px-3 pb-2 max-h-36 overflow-y-auto">
          {anomaly.anomalies.slice(0, 20).map((a, i) => (
            <div
              key={i}
              className="flex items-center gap-2 py-0.5 text-xs font-mono border-b border-slate-700/50 last:border-0"
            >
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  a.severity === 'critical' ? 'bg-red-500' : 'bg-amber-500'
                }`}
              />
              <span className="text-slate-400 w-36 flex-shrink-0 truncate">
                {a.timestamp.slice(0, 19).replace('T', ' ')}
              </span>
              <span className="text-slate-200 w-20 flex-shrink-0">
                {formatVal(a.value)} {anomaly.unit}
              </span>
              <span className="text-slate-500 truncate">{a.reason}</span>
            </div>
          ))}
          {anomaly.anomalies.length > 20 && (
            <p className="text-xs text-slate-500 mt-1">
              ...and {anomaly.anomalies.length - 20} more
            </p>
          )}
        </div>
      )}

      {/* Stats footer */}
      <div className="px-3 py-1.5 bg-slate-900/50 text-xs font-mono text-slate-400 flex flex-wrap gap-x-3 border-t border-slate-700">
        <span>min={formatVal(anomaly.min)}</span>
        <span>max={formatVal(anomaly.max)}</span>
        <span>μ={formatVal(anomaly.mean)}</span>
        <span>σ={formatVal(anomaly.std_dev)}</span>
        <span className="ml-auto">n={anomaly.sample_count}</span>
      </div>

      {/* Actions */}
      <div className="px-3 py-1.5 flex gap-2 border-t border-slate-700">
        <button
          onClick={() => exportAnomalyCSV(anomaly)}
          className="text-xs text-slate-400 hover:text-cyan-400 transition-colors"
        >
          Export CSV
        </button>
      </div>
    </div>
  );
};
