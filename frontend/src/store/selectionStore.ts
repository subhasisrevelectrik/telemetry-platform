import { create } from 'zustand';
import { type TimeRange, getDefaultTimeRange, getPresetRange } from '../utils/timeRanges';

export interface SelectedSignal {
  message_name: string;
  signal_name: string;
}

interface SelectionState {
  // Selected vehicle
  selectedVehicle: string | null;
  setSelectedVehicle: (vehicleId: string | null) => void;

  // Time range
  timeRange: TimeRange;
  setTimeRange: (range: TimeRange) => void;

  // Selected signals for charting
  selectedSignals: SelectedSignal[];
  addSignal: (signal: SelectedSignal) => void;
  removeSignal: (signal: SelectedSignal) => void;
  clearSignals: () => void;
  toggleSignal: (signal: SelectedSignal) => void;

  // Max points for downsampling
  maxPoints: number;
  setMaxPoints: (points: number) => void;

  // Sidebar collapsed state
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

export const useSelectionStore = create<SelectionState>((set) => ({
  selectedVehicle: null,
  setSelectedVehicle: (vehicleId) => set({ selectedVehicle: vehicleId }),

  timeRange: getDefaultTimeRange(),
  setTimeRange: (range) => set({ timeRange: range }),

  selectedSignals: [],
  addSignal: (signal) =>
    set((state) => ({
      selectedSignals: [...state.selectedSignals, signal],
    })),
  removeSignal: (signal) =>
    set((state) => ({
      selectedSignals: state.selectedSignals.filter(
        (s) => !(s.message_name === signal.message_name && s.signal_name === signal.signal_name)
      ),
    })),
  clearSignals: () => set({ selectedSignals: [] }),
  toggleSignal: (signal) =>
    set((state) => {
      const exists = state.selectedSignals.some(
        (s) => s.message_name === signal.message_name && s.signal_name === signal.signal_name
      );
      if (exists) {
        return {
          selectedSignals: state.selectedSignals.filter(
            (s) => !(s.message_name === signal.message_name && s.signal_name === signal.signal_name)
          ),
        };
      } else {
        return {
          selectedSignals: [...state.selectedSignals, signal],
        };
      }
    }),

  maxPoints: Number(import.meta.env.VITE_DEFAULT_MAX_POINTS) || 500,
  setMaxPoints: (points) => set({ maxPoints: points }),

  sidebarCollapsed: false,
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
}));
