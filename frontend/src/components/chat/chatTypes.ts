/**
 * TypeScript interfaces for the AI chatbot feature.
 */

// ---------------------------------------------------------------------------
// Chart types
// ---------------------------------------------------------------------------

export interface ChatSignalSpec {
  vehicle_id: string;
  message_name: string;
  signal_name: string;
  y_axis?: 'left' | 'right';
}

export interface ChartAnnotation {
  timestamp: string;
  label: string;
  color: string;
}

export interface ChartThresholdLine {
  value: number;
  label: string;
  color: string;
  signal_name?: string;
}

export interface ChartSignalData {
  timestamps: string[];
  values: number[];
  unit: string;
  y_axis?: 'left' | 'right';
}

/** A chart produced by the AI — includes fetched data ready for rendering. */
export interface ChatChart {
  chart_type: 'time_series' | 'histogram' | 'scatter' | 'box_plot';
  title: string;
  /** Key: "MessageName.SignalName" */
  data: Record<string, ChartSignalData>;
  threshold_lines: ChartThresholdLine[];
  annotations: ChartAnnotation[];
  start_time?: string;
  end_time?: string;
}

// ---------------------------------------------------------------------------
// Anomaly types
// ---------------------------------------------------------------------------

export interface AnomalyPoint {
  timestamp: string;
  value: number;
  reason: string;
  severity: 'warning' | 'critical';
}

export interface AnomalyResult {
  vehicle_id: string;
  signal_name: string;
  message_name: string;
  unit: string;
  min: number;
  max: number;
  mean: number;
  std_dev: number;
  p5: number;
  p50: number;
  p95: number;
  sample_count: number;
  anomalies: AnomalyPoint[];
  threshold_low?: number;
  threshold_high?: number;
}

// ---------------------------------------------------------------------------
// Chat message types
// ---------------------------------------------------------------------------

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  charts?: ChatChart[];
  anomalies?: AnomalyResult[];
  suggestions?: string[];
  timestamp: Date;
}

// ---------------------------------------------------------------------------
// API types
// ---------------------------------------------------------------------------

export interface ChatRequest {
  message: string;
  conversation_id?: string;
  vehicle_context?: string;
}

export interface ChatResponseBody {
  text: string;
  charts: ChatChart[];
  anomalies: AnomalyResult[];
  suggestions: string[];
}

export interface ChatApiResponse {
  conversation_id: string;
  response: ChatResponseBody;
}

// ---------------------------------------------------------------------------
// Usage stats
// ---------------------------------------------------------------------------

export interface UsageStats {
  date: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_calls: number;
  avg_tokens_per_call: number;
}
