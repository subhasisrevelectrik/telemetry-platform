/**
 * AI Telemetry Assistant — sliding right-side panel.
 *
 * Opens as a 420px flex sibling to the main content area so the dashboard
 * shrinks proportionally (no overlay).
 */
import { FC, useEffect, useRef } from 'react';
import { Bot, X, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import { useChatStore } from './useChatStore';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { ChatContext } from './ChatContext';
import { useSelectionStore } from '@/store/selectionStore';

// Starter suggestions when panel is opened
const SUGGESTIONS_WITH_VEHICLE = [
  'What signals are available for this vehicle?',
  'Show me all battery-related signals',
  'Check for temperature anomalies',
  'Plot motor RPM over the last hour',
];

const SUGGESTIONS_NO_VEHICLE = [
  'What vehicles are in the database?',
  'What is a CAN bus?',
  'Explain battery state of charge estimation',
  'What is cell voltage imbalance?',
];

export const ChatPanel: FC = () => {
  const { isOpen, messages, isLoading, error, sendMessage, clearConversation, dismissError, togglePanel } =
    useChatStore();
  const selectedVehicle = useSelectionStore((s) => s.selectedVehicle);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

  const handleSend = (text: string) => {
    sendMessage(text, selectedVehicle);
  };

  const handleSuggestionClick = (text: string) => {
    sendMessage(text, selectedVehicle);
  };

  const starterSuggestions = selectedVehicle
    ? SUGGESTIONS_WITH_VEHICLE
    : SUGGESTIONS_NO_VEHICLE;

  return (
    <aside
      className={clsx(
        'flex flex-col border-l border-slate-700 bg-slate-800 transition-all duration-300 overflow-hidden flex-shrink-0',
        isOpen ? 'w-[420px]' : 'w-0'
      )}
      aria-label="AI Assistant panel"
    >
      {isOpen && (
        <>
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 bg-slate-800 flex-shrink-0">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5 text-cyan-400" />
              <span className="text-sm font-semibold text-slate-200">
                Telemetry Assistant
              </span>
            </div>
            <div className="flex items-center gap-2">
              {messages.length > 0 && (
                <button
                  onClick={clearConversation}
                  title="Clear conversation"
                  className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-700 rounded-md transition-colors"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
              <button
                onClick={togglePanel}
                title="Close panel"
                className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-700 rounded-md transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Vehicle/time context strip */}
          <ChatContext />

          {/* Messages area */}
          <div className="flex-1 overflow-y-auto p-3 space-y-1">
            {/* Empty state with starter suggestions */}
            {messages.length === 0 && !isLoading && (
              <div className="flex flex-col items-center justify-center h-full text-center px-4 py-8">
                <Bot className="h-12 w-12 text-slate-600 mb-3" />
                <p className="text-sm text-slate-400 mb-1">
                  Ask about your telemetry data
                </p>
                <p className="text-xs text-slate-600 mb-4">
                  I can visualize signals, detect anomalies, and answer questions about CAN bus data.
                </p>
                <div className="flex flex-col gap-2 w-full max-w-xs">
                  {starterSuggestions.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => handleSuggestionClick(s)}
                      className="px-3 py-2 text-xs text-left rounded-lg border border-slate-600
                                 text-slate-400 hover:border-cyan-500 hover:text-cyan-400
                                 hover:bg-slate-800 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Message list */}
            {messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                onSuggestionClick={handleSuggestionClick}
              />
            ))}

            {/* Typing indicator */}
            {isLoading && (
              <div className="flex items-center gap-2 text-xs text-slate-500 py-2">
                <div className="flex gap-1">
                  <span
                    className="h-1.5 w-1.5 rounded-full bg-slate-500 animate-bounce"
                    style={{ animationDelay: '0ms' }}
                  />
                  <span
                    className="h-1.5 w-1.5 rounded-full bg-slate-500 animate-bounce"
                    style={{ animationDelay: '150ms' }}
                  />
                  <span
                    className="h-1.5 w-1.5 rounded-full bg-slate-500 animate-bounce"
                    style={{ animationDelay: '300ms' }}
                  />
                </div>
                <span>Thinking…</span>
              </div>
            )}

            {/* Error banner */}
            {error && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-red-900/30 border border-red-800/50 text-xs text-red-300">
                <span className="flex-1">{error}</span>
                <button
                  onClick={dismissError}
                  className="text-red-400 hover:text-red-200"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input area */}
          <ChatInput onSend={handleSend} isLoading={isLoading} />
        </>
      )}
    </aside>
  );
};
