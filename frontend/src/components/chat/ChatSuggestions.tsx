/**
 * Clickable suggestion chips shown after an AI message.
 */
import { FC } from 'react';

interface ChatSuggestionsProps {
  suggestions: string[];
  onSelect: (suggestion: string) => void;
}

export const ChatSuggestions: FC<ChatSuggestionsProps> = ({ suggestions, onSelect }) => {
  if (!suggestions || suggestions.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {suggestions.map((s, i) => (
        <button
          key={i}
          onClick={() => onSelect(s)}
          className="px-3 py-1.5 text-xs rounded-full border border-slate-600 text-slate-300
                     hover:border-cyan-500 hover:text-cyan-400 hover:bg-slate-800
                     transition-colors cursor-pointer text-left"
        >
          {s}
        </button>
      ))}
    </div>
  );
};
