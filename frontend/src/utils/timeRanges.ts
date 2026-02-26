export interface TimeRange {
  start: Date;
  end: Date;
  preset?: string | null;
}

export interface TimePreset {
  label: string;
  value: string;
  getDuration: () => number;
}

export const TIME_PRESETS: TimePreset[] = [
  {
    label: 'Last 1 Hour',
    value: '1h',
    getDuration: () => 60 * 60 * 1000,
  },
  {
    label: 'Last 6 Hours',
    value: '6h',
    getDuration: () => 6 * 60 * 60 * 1000,
  },
  {
    label: 'Last 24 Hours',
    value: '24h',
    getDuration: () => 24 * 60 * 60 * 1000,
  },
  {
    label: 'Last 7 Days',
    value: '7d',
    getDuration: () => 7 * 24 * 60 * 60 * 1000,
  },
];

export function getDefaultTimeRange(): TimeRange {
  const end = new Date();
  const start = new Date(end.getTime() - 60 * 60 * 1000);
  return { start, end, preset: '1h' };
}

export function getPresetRange(preset: string): TimeRange {
  const presetObj = TIME_PRESETS.find((p) => p.value === preset);

  if (!presetObj) {
    const end = new Date();
    const start = new Date(end.getTime() - 60 * 60 * 1000);
    return { start, end, preset: '1h' };
  }

  const end = new Date();
  const start = new Date(end.getTime() - presetObj.getDuration());

  return { start, end, preset };
}

export function validateTimeRange(start: Date, end: Date): string | null {
  if (start >= end) {
    return 'Start time must be before end time';
  }

  const maxDuration = 30 * 24 * 60 * 60 * 1000;
  if (end.getTime() - start.getTime() > maxDuration) {
    return 'Time range cannot exceed 30 days';
  }

  return null;
}
