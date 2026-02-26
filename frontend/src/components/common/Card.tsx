import { FC, ReactNode } from 'react';
import clsx from 'clsx';

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
}

export const Card: FC<CardProps> = ({ title, children, className }) => {
  return (
    <div className={clsx('bg-slate-800 rounded-lg border border-slate-700 p-4', className)}>
      {title && <h3 className="text-lg font-semibold text-slate-200 mb-3">{title}</h3>}
      {children}
    </div>
  );
};
