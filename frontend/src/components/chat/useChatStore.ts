/**
 * Zustand store for the AI chat panel state.
 */
import { create } from 'zustand';
import { startChat, pollChatStatus } from './chatApi';
import type { ChatChart, ChatMessage } from './chatTypes';
import { useSelectionStore } from '@/store/selectionStore';
import { useChartStore } from '@/store/chartStore';
import type { QueryResponse, SignalData, DataPoint } from '@/api/types';

const POLL_INITIAL_DELAY_MS = 1000; // first poll after 1 s
const POLL_INTERVAL_MS = 2000;      // subsequent polls every 2 s
const POLL_MAX_ATTEMPTS = 90;       // give up after 3 minutes

interface ChatState {
  /** Whether the chat panel is visible */
  isOpen: boolean;
  /** Current conversation messages */
  messages: ChatMessage[];
  /** Backend conversation ID for multi-turn history */
  conversationId: string | null;
  /** Loading state while waiting for AI response */
  isLoading: boolean;
  /** Error message if the last request failed */
  error: string | null;

  /** Toggle the chat panel open/closed */
  togglePanel: () => void;
  /** Open the chat panel */
  openPanel: () => void;
  /** Send a message and append both user msg and AI response */
  sendMessage: (text: string, vehicleId: string | null) => Promise<void>;
  /** Clear conversation history */
  clearConversation: () => void;
  /** Copy a chat chart to the main dashboard */
  addChartToDashboard: (chart: ChatChart) => void;
  /** Dismiss the current error */
  dismissError: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  isOpen: false,
  messages: [],
  conversationId: null,
  isLoading: false,
  error: null,

  togglePanel: () => set((state) => ({ isOpen: !state.isOpen })),

  openPanel: () => set({ isOpen: true }),

  sendMessage: async (text: string, vehicleId: string | null) => {
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    };

    set((state) => ({
      messages: [...state.messages, userMsg],
      isLoading: true,
      error: null,
    }));

    try {
      // --- 1. Start the async job (returns immediately) ---
      const { job_id, conversation_id } = await startChat({
        message: text,
        conversation_id: get().conversationId ?? undefined,
        vehicle_context: vehicleId ?? undefined,
      });

      set({ conversationId: conversation_id });

      // --- 2. Poll until complete ---
      await new Promise((resolve) => setTimeout(resolve, POLL_INITIAL_DELAY_MS));

      for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt++) {
        const status = await pollChatStatus(job_id);

        if (status.status === 'complete' && status.response) {
          const assistantMsg: ChatMessage = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: status.response.text,
            charts: status.response.charts,
            anomalies: status.response.anomalies,
            suggestions: status.response.suggestions,
            timestamp: new Date(),
          };

          set({
            messages: [...get().messages, assistantMsg],
            conversationId: status.conversation_id ?? get().conversationId,
            isLoading: false,
          });
          return;
        }

        if (status.status === 'error') {
          throw new Error(status.error ?? 'Chat processing failed');
        }

        // Still pending — wait before next poll
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      }

      throw new Error('Chat timed out after 3 minutes');
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : 'Failed to get a response from the AI assistant.';
      set({ isLoading: false, error: message });
    }
  },

  clearConversation: () =>
    set({ messages: [], conversationId: null, error: null }),

  addChartToDashboard: (chart: ChatChart) => {
    // Convert ChatChart.data to QueryResponse format and push to chartStore
    const signalDataList: SignalData[] = Object.entries(chart.data).map(
      ([key, signalData]) => {
        // key is "MessageName.SignalName" — use signal name for display
        const signalName = key.split('.').slice(1).join('.') || key;
        const dataPoints: DataPoint[] = signalData.timestamps.map((ts, i) => ({
          t: new Date(ts).getTime(),
          v: signalData.values[i] ?? 0,
        }));
        return {
          name: signalName,
          unit: signalData.unit,
          data: dataPoints,
        };
      }
    );

    if (signalDataList.length === 0) return;

    const queryResponse: QueryResponse = {
      signals: signalDataList,
      query_stats: {
        rows_scanned: 0,
        bytes_scanned: 0,
        duration_ms: 0,
      },
    };

    // Push to chart store so the main dashboard immediately renders it
    useChartStore.getState().setQueryData(queryResponse);

    // Also update selectionStore signals for consistency
    const selectionStore = useSelectionStore.getState();
    Object.entries(chart.data).forEach(([key]) => {
      const dotIdx = key.indexOf('.');
      if (dotIdx === -1) return;
      const message_name = key.slice(0, dotIdx);
      const signal_name = key.slice(dotIdx + 1);
      selectionStore.addSignal({ message_name, signal_name });
    });

    // Update time range if available
    if (chart.start_time && chart.end_time) {
      selectionStore.setTimeRange({
        start: new Date(chart.start_time),
        end: new Date(chart.end_time),
        preset: null,
      });
    }
  },

  dismissError: () => set({ error: null }),
}));
