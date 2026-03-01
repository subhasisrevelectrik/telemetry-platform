/**
 * Single chat message bubble — handles user and assistant messages.
 * Assistant messages render text, charts, anomaly cards, and suggestion chips.
 */
import { FC } from 'react';
import type { ChatMessage as ChatMessageType } from './chatTypes';
import { ChatChart } from './ChatChart';
import { ChatAnomalyCard } from './ChatAnomalyCard';
import { ChatSuggestions } from './ChatSuggestions';
import { Bot, User } from 'lucide-react';
import clsx from 'clsx';

interface ChatMessageProps {
  message: ChatMessageType;
  onSuggestionClick: (text: string) => void;
}

/**
 * Very lightweight markdown rendering — handles bold, italic, inline code,
 * and code blocks without adding a heavy dependency.
 */
function renderMarkdown(text: string): string {
  return text
    // Code blocks
    .replace(/```[\s\S]*?```/g, (m) => {
      const code = m.slice(3, -3).replace(/^\w*\n/, '');
      return `<pre class="bg-slate-900 border border-slate-700 rounded p-2 my-1 text-xs font-mono overflow-x-auto whitespace-pre-wrap">${escHtml(code)}</pre>`;
    })
    // Inline code
    .replace(/`([^`]+)`/g, (_, c) => `<code class="bg-slate-900 px-1 rounded text-cyan-300 font-mono text-xs">${escHtml(c)}</code>`)
    // Bold
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="text-slate-200">$1</strong>')
    // Italic
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    // Line breaks
    .replace(/\n/g, '<br/>');
}

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export const ChatMessage: FC<ChatMessageProps> = ({ message, onSuggestionClick }) => {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end mb-3">
        <div className="flex items-start gap-2 max-w-[85%]">
          <div className="bg-cyan-900/40 border border-cyan-800/40 rounded-xl rounded-tr-sm px-3 py-2 text-sm text-slate-200">
            {message.content}
          </div>
          <div className="flex-shrink-0 w-6 h-6 rounded-full bg-slate-700 flex items-center justify-center mt-0.5">
            <User className="h-3.5 w-3.5 text-slate-300" />
          </div>
        </div>
      </div>
    );
  }

  // Assistant message
  const hasCharts = message.charts && message.charts.length > 0;
  const hasAnomalies = message.anomalies && message.anomalies.length > 0;
  const hasSuggestions = message.suggestions && message.suggestions.length > 0;

  return (
    <div className="flex justify-start mb-3">
      <div className="flex items-start gap-2 max-w-full w-full">
        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-cyan-900 flex items-center justify-center mt-0.5">
          <Bot className="h-3.5 w-3.5 text-cyan-400" />
        </div>
        <div className="flex-1 min-w-0">
          {/* Text */}
          {message.content && (
            <div
              className={clsx(
                'text-sm text-slate-300 leading-relaxed',
                'bg-slate-800/60 border border-slate-700/60 rounded-xl rounded-tl-sm px-3 py-2'
              )}
              dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
            />
          )}

          {/* Charts */}
          {hasCharts &&
            message.charts!.map((chart, i) => <ChatChart key={i} chart={chart} />)}

          {/* Anomaly cards */}
          {hasAnomalies &&
            message.anomalies!.map((anomaly, i) => (
              <ChatAnomalyCard key={i} anomaly={anomaly} />
            ))}

          {/* Suggestions */}
          {hasSuggestions && (
            <ChatSuggestions
              suggestions={message.suggestions!}
              onSelect={onSuggestionClick}
            />
          )}

          {/* Timestamp */}
          <div className="mt-1 text-[10px] text-slate-600">
            {message.timestamp.toLocaleTimeString(undefined, {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
