import { FC, useState } from 'react';
import { useMessages, useSignals } from '@/api/hooks';
import { useSelectionStore } from '@/store/selectionStore';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { getSignalColor } from '@/utils/colors';
import { ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';

export const SignalSelector: FC = () => {
  const selectedVehicle = useSelectionStore((state) => state.selectedVehicle);
  const { selectedSignals, toggleSignal, clearSignals } = useSelectionStore();
  const [expandedMessages, setExpandedMessages] = useState<Set<string>>(new Set());

  const {
    data: messages,
    isLoading: messagesLoading,
    error: messagesError,
    refetch: refetchMessages,
  } = useMessages(selectedVehicle || '');

  const toggleMessage = (messageName: string) => {
    setExpandedMessages((prev) => {
      const next = new Set(prev);
      if (next.has(messageName)) {
        next.delete(messageName);
      } else {
        next.add(messageName);
      }
      return next;
    });
  };

  if (!selectedVehicle) {
    return (
      <Card title="Signals">
        <p className="text-sm text-slate-400 text-center py-4">
          Select a vehicle first
        </p>
      </Card>
    );
  }

  if (messagesLoading) {
    return (
      <Card title="Signals">
        <LoadingSpinner size="sm" text="Loading messages..." />
      </Card>
    );
  }

  if (messagesError) {
    return (
      <Card title="Signals">
        <ErrorBanner
          message={messagesError instanceof Error ? messagesError.message : 'Failed to load messages'}
          onRetry={() => refetchMessages()}
        />
      </Card>
    );
  }

  if (!messages || messages.length === 0) {
    return (
      <Card title="Signals">
        <p className="text-sm text-slate-400 text-center py-4">
          No messages found
        </p>
      </Card>
    );
  }

  const maxSignals = Number(import.meta.env.VITE_MAX_SIGNALS) || 10;
  const warningThreshold = Math.floor(maxSignals * 0.8);

  return (
    <Card title="Signals">
      {/* Selection Summary */}
      <div className="flex items-center justify-between mb-3 pb-3 border-b border-slate-700">
        <span className="text-sm text-slate-400">
          {selectedSignals.length} selected
          {selectedSignals.length >= warningThreshold && (
            <AlertTriangle className="inline h-4 w-4 ml-2 text-amber-500" />
          )}
        </span>
        {selectedSignals.length > 0 && (
          <button
            onClick={clearSignals}
            className="text-xs text-primary-400 hover:text-primary-300"
          >
            Clear All
          </button>
        )}
      </div>

      {/* Warning Message */}
      {selectedSignals.length >= warningThreshold && (
        <div className="mb-3 p-2 bg-amber-900/20 border border-amber-500/50 rounded text-xs text-amber-400">
          {selectedSignals.length >= maxSignals
            ? `Maximum ${maxSignals} signals reached. Deselect signals to add more.`
            : `Warning: Selecting too many signals may impact performance.`}
        </div>
      )}

      {/* Message/Signal Tree */}
      <div className="space-y-1 max-h-96 overflow-y-auto">
        {messages.map((message) => (
          <MessageGroup
            key={message.message_name}
            message={message}
            vehicleId={selectedVehicle}
            isExpanded={expandedMessages.has(message.message_name)}
            onToggle={() => toggleMessage(message.message_name)}
            selectedSignals={selectedSignals}
            onToggleSignal={toggleSignal}
            maxSignals={maxSignals}
          />
        ))}
      </div>
    </Card>
  );
};

// Subcomponent for each message group
interface MessageGroupProps {
  message: any;
  vehicleId: string;
  isExpanded: boolean;
  onToggle: () => void;
  selectedSignals: Array<{ message_name: string; signal_name: string }>;
  onToggleSignal: (signal: { message_name: string; signal_name: string }) => void;
  maxSignals: number;
}

const MessageGroup: FC<MessageGroupProps> = ({
  message,
  vehicleId,
  isExpanded,
  onToggle,
  selectedSignals,
  onToggleSignal,
  maxSignals,
}) => {
  const {
    data: signals,
    isLoading,
    error,
  } = useSignals(vehicleId, message.message_name);

  const signalsInMessage = selectedSignals.filter(
    (s) => s.message_name === message.message_name
  ).length;

  return (
    <div className="border border-slate-700 rounded-md overflow-hidden">
      {/* Message Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-3 py-2 bg-slate-800 hover:bg-slate-700 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-slate-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-slate-400" />
          )}
          <span className="text-sm text-slate-200 font-medium">
            {message.message_name}
          </span>
          {signalsInMessage > 0 && (
            <span className="text-xs bg-primary-500/20 text-primary-400 px-2 py-0.5 rounded">
              {signalsInMessage}
            </span>
          )}
        </div>
        <span className="text-xs text-slate-500">
          {message.signal_count} signals
        </span>
      </button>

      {/* Signal List */}
      {isExpanded && (
        <div className="bg-slate-900/50 p-2">
          {isLoading && (
            <div className="py-4">
              <LoadingSpinner size="sm" text="Loading signals..." />
            </div>
          )}

          {error && (
            <p className="text-xs text-red-400 py-2">
              Failed to load signals
            </p>
          )}

          {signals && signals.length > 0 && (
            <div className="space-y-1">
              {signals.map((signal, index) => {
                const isSelected = selectedSignals.some(
                  (s) =>
                    s.message_name === message.message_name &&
                    s.signal_name === signal.signal_name
                );
                const color = getSignalColor(
                  selectedSignals.findIndex(
                    (s) =>
                      s.message_name === message.message_name &&
                      s.signal_name === signal.signal_name
                  )
                );
                const canSelect = isSelected || selectedSignals.length < maxSignals;

                return (
                  <label
                    key={signal.signal_name}
                    className={clsx(
                      'flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition-colors',
                      canSelect
                        ? 'hover:bg-slate-800'
                        : 'opacity-50 cursor-not-allowed'
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() =>
                        onToggleSignal({
                          message_name: message.message_name,
                          signal_name: signal.signal_name,
                        })
                      }
                      disabled={!canSelect}
                      className="h-4 w-4 rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                    />
                    {isSelected && (
                      <div
                        className="h-3 w-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: color }}
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-300 truncate">
                        {signal.signal_name}
                      </p>
                      {signal.unit && (
                        <p className="text-xs text-slate-500">{signal.unit}</p>
                      )}
                    </div>
                  </label>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
