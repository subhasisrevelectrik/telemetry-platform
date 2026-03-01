/**
 * Chat input area with auto-complete for signal names.
 */
import {
  FC,
  FormEvent,
  KeyboardEvent,
  useRef,
  useState,
  useEffect,
} from 'react';
import { Send } from 'lucide-react';
import { useSelectionStore } from '@/store/selectionStore';
import { useMessages } from '@/api/hooks';

interface ChatInputProps {
  onSend: (text: string) => void;
  isLoading: boolean;
}

const SIGNAL_AUTOCOMPLETE_TRIGGERS = /\b[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]*$/;

export const ChatInput: FC<ChatInputProps> = ({ onSend, isLoading }) => {
  const [value, setValue] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const selectedVehicle = useSelectionStore((s) => s.selectedVehicle);
  const { data: messages } = useMessages(selectedVehicle);

  // Flatten all signal names for autocomplete
  const allSignalNames: string[] = [];
  // We can't easily get all signal names without fetching per-message,
  // so use message names as autocomplete candidates for now
  if (messages) {
    allSignalNames.push(...messages.map((m) => m.message_name));
  }

  const handleInput = (val: string) => {
    setValue(val);

    // Check if the cursor is on a potential signal name pattern
    const match = val.match(SIGNAL_AUTOCOMPLETE_TRIGGERS);
    if (match && allSignalNames.length > 0) {
      const prefix = match[0].toLowerCase();
      const filtered = allSignalNames.filter((s) =>
        s.toLowerCase().startsWith(prefix)
      );
      setSuggestions(filtered.slice(0, 5));
      setShowSuggestions(filtered.length > 0);
    } else {
      setShowSuggestions(false);
    }
  };

  const handleSuggestionClick = (s: string) => {
    const match = value.match(SIGNAL_AUTOCOMPLETE_TRIGGERS);
    if (match) {
      setValue(value.slice(0, value.length - match[0].length) + s);
    }
    setShowSuggestions(false);
    textareaRef.current?.focus();
  };

  const handleSubmit = (e?: FormEvent) => {
    e?.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setValue('');
    setShowSuggestions(false);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
    if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
  }, [value]);

  return (
    <div className="border-t border-slate-700 bg-slate-800 p-3">
      {/* Vehicle context hint */}
      <div className="text-xs text-slate-500 font-mono mb-2 px-0.5">
        {selectedVehicle ? (
          <span>
            <span className="text-slate-600">Context: </span>
            <span className="text-cyan-600">{selectedVehicle}</span>
          </span>
        ) : (
          <span className="text-slate-600">
            Select a vehicle to query data, or ask a general question
          </span>
        )}
      </div>

      <div className="relative">
        {/* Signal autocomplete dropdown */}
        {showSuggestions && (
          <div className="absolute bottom-full left-0 mb-1 w-full bg-slate-900 border border-slate-600 rounded-lg overflow-hidden shadow-xl z-10">
            {suggestions.map((s, i) => (
              <button
                key={i}
                onMouseDown={(e) => {
                  e.preventDefault(); // prevent textarea blur
                  handleSuggestionClick(s);
                }}
                className="w-full text-left px-3 py-1.5 text-xs font-mono text-slate-300
                           hover:bg-slate-700 hover:text-cyan-400 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => handleInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isLoading
                ? 'Waiting for response...'
                : 'Ask about your telemetry data...'
            }
            disabled={isLoading}
            rows={1}
            className="flex-1 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm
                       text-slate-200 placeholder-slate-600 resize-none overflow-y-auto
                       focus:outline-none focus:ring-1 focus:ring-cyan-500 focus:border-cyan-500
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors"
            style={{ minHeight: '38px', maxHeight: '120px' }}
          />
          <button
            type="submit"
            disabled={!value.trim() || isLoading}
            className="flex-shrink-0 p-2 rounded-lg bg-cyan-600 hover:bg-cyan-500
                       disabled:bg-slate-700 disabled:cursor-not-allowed
                       text-white transition-colors"
            aria-label="Send message"
          >
            {isLoading ? (
              <svg
                className="h-4 w-4 animate-spin"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
            ) : (
              <Send className="h-4 w-4" />
            )}
          </button>
        </form>
        <p className="mt-1 text-[10px] text-slate-600 px-0.5">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
};
