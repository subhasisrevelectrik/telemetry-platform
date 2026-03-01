/**
 * Toggle button for the AI chat panel.
 * Placed in the navigation bar (top right area of TopBar).
 */
import { FC, useEffect } from 'react';
import { Bot } from 'lucide-react';
import { useChatStore } from './useChatStore';
import clsx from 'clsx';

export const ChatToggle: FC = () => {
  const { isOpen, togglePanel } = useChatStore();

  // Keyboard shortcut: Ctrl+/ or Cmd+/
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault();
        togglePanel();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [togglePanel]);

  return (
    <button
      onClick={togglePanel}
      title={isOpen ? 'Close AI Assistant (Ctrl+/)' : 'Open AI Assistant (Ctrl+/)'}
      aria-label={isOpen ? 'Close AI assistant' : 'Open AI assistant'}
      className={clsx(
        'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
        isOpen
          ? 'bg-cyan-600 text-white hover:bg-cyan-500'
          : 'bg-slate-700 text-slate-300 hover:bg-slate-600 hover:text-slate-100'
      )}
    >
      <Bot className="h-4 w-4" />
      <span className="hidden sm:inline">AI Assistant</span>
    </button>
  );
};
