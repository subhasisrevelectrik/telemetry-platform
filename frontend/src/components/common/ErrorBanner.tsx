import { FC } from 'react';
import { Button } from './Button';

interface ErrorBannerProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  onDismiss?: () => void;
}

export const ErrorBanner: FC<ErrorBannerProps> = ({
  title = 'Error',
  message,
  onRetry,
  onDismiss,
}) => {
  return (
    <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="font-semibold text-red-400">{title}</p>
          <p className="text-sm text-red-300 mt-1">{message}</p>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-red-400 hover:text-red-300 ml-4"
            aria-label="Dismiss"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        )}
      </div>
      {onRetry && (
        <div className="mt-3">
          <Button variant="danger" size="sm" onClick={onRetry}>
            Retry
          </Button>
        </div>
      )}
    </div>
  );
};
