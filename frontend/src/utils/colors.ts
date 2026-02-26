/**
 * Signal color palette - 10 distinct colors for chart lines
 */
const SIGNAL_COLORS = [
  '#06b6d4', // cyan-500
  '#8b5cf6', // violet-500
  '#f59e0b', // amber-500
  '#10b981', // emerald-500
  '#ef4444', // red-500
  '#3b82f6', // blue-500
  '#ec4899', // pink-500
  '#14b8a6', // teal-500
  '#f97316', // orange-500
  '#6366f1', // indigo-500
];

/**
 * Get a color for a signal by index (cycles through palette)
 */
export function getSignalColor(index: number): string {
  return SIGNAL_COLORS[index % SIGNAL_COLORS.length];
}

/**
 * Get a semantic color based on signal name patterns
 */
export function getSemanticColor(signalName: string): string {
  const lower = signalName.toLowerCase();

  if (lower.includes('voltage')) return '#f59e0b'; // amber
  if (lower.includes('current')) return '#ef4444'; // red
  if (lower.includes('temp')) return '#f97316'; // orange
  if (lower.includes('soc')) return '#10b981'; // emerald
  if (lower.includes('rpm')) return '#8b5cf6'; // violet
  if (lower.includes('torque') || lower.includes('power')) return '#06b6d4'; // cyan
  if (lower.includes('flow')) return '#14b8a6'; // teal
  if (lower.includes('pressure')) return '#3b82f6'; // blue

  // Default: use index-based color
  return SIGNAL_COLORS[0];
}

/**
 * Convert hex color to RGBA
 */
export function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
