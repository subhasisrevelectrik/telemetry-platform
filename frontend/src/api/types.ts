/**
 * TypeScript interfaces matching backend/src/models.py
 */

export interface Vehicle {
  vehicle_id: string;
  first_seen: string; // ISO datetime
  last_seen: string;
  frame_count: number;
}

export interface Session {
  date: string; // YYYY-MM-DD
  start_time: string; // ISO datetime
  end_time: string;
  sample_count: number;
}

export interface Message {
  message_name: string;
  sample_count: number;
}

export interface Signal {
  signal_name: string;
  unit: string;
  min_value: number;
  max_value: number;
  avg_value: number;
}

export interface SignalRequest {
  message_name: string;
  signal_name: string;
}

export interface QueryRequest {
  signals: SignalRequest[];
  start_time: string; // ISO datetime
  end_time: string;
}

export interface DataPoint {
  t: number; // Timestamp in milliseconds
  v: number; // Value
}

export interface SignalData {
  name: string;
  unit: string;
  data: DataPoint[];
}

export interface QueryStats {
  rows_scanned: number;
  bytes_scanned: number;
  duration_ms: number;
  downsampled?: boolean;
  original_points?: number;
  downsampled_points?: number;
}

export interface QueryResponse {
  signals: SignalData[];
  query_stats: QueryStats;
}

export interface HealthResponse {
  status: string;
  version: string;
  mode: string;
}
