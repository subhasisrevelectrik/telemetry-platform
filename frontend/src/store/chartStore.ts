import { create } from 'zustand';
import type{ QueryResponse } from '@/api/types';

interface ChartState {
  // Current query result
  queryData: QueryResponse | null;
  setQueryData: (data: QueryResponse | null) => void;

  // Visible signals (for legend toggle)
  visibleSignals: Set<string>;
  toggleSignal: (signalName: string) => void;
  showAllSignals: () => void;
  hideAllSignals: () => void;
  resetVisibleSignals: () => void;

  // Zoom state
  zoomRange: { min: number | null; max: number | null };
  setZoomRange: (min: number | null, max: number | null) => void;
  resetZoom: () => void;
}

export const useChartStore = create<ChartState>((set, get) => ({
  queryData: null,
  setQueryData: (data) => {
    set({ queryData: data });

    // Initialize visible signals when new data is loaded
    if (data) {
      const allSignalNames = new Set(data.signals.map((s) => s.name));
      set({ visibleSignals: allSignalNames });
    }
  },

  visibleSignals: new Set(),
  toggleSignal: (signalName) =>
    set((state) => {
      const newVisible = new Set(state.visibleSignals);
      if (newVisible.has(signalName)) {
        newVisible.delete(signalName);
      } else {
        newVisible.add(signalName);
      }
      return { visibleSignals: newVisible };
    }),

  showAllSignals: () =>
    set((state) => {
      if (!state.queryData) return state;
      const allSignalNames = new Set(state.queryData.signals.map((s) => s.name));
      return { visibleSignals: allSignalNames };
    }),

  hideAllSignals: () => set({ visibleSignals: new Set() }),

  resetVisibleSignals: () =>
    set((state) => {
      if (!state.queryData) return state;
      const allSignalNames = new Set(state.queryData.signals.map((s) => s.name));
      return { visibleSignals: allSignalNames };
    }),

  zoomRange: { min: null, max: null },
  setZoomRange: (min, max) => set({ zoomRange: { min, max } }),
  resetZoom: () => set({ zoomRange: { min: null, max: null } }),
}));
