import {AlertTriangle, FileQuestion, RefreshCw} from 'lucide-react';
import type {ReactNode} from 'react';

import {NavLink} from '../links.tsx';
import {listPath} from '../routes.ts';

export function LoadingState({label}: {label: string}) {
  return (
    <p role="status" aria-busy="true" className="px-4 py-10 text-center text-sm text-stone-500">
      {label}
    </p>
  );
}

export function EmptyState({title, detail, action}: {title: string; detail: string; action?: ReactNode}) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-8 text-center">
      <p className="text-sm font-semibold text-stone-800">{title}</p>
      <p className="mt-1 text-xs text-stone-500">{detail}</p>
      {action !== undefined && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({error, onRetry}: {error: Error; onRetry: () => void}) {
  return (
    <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50/60 p-6 text-center">
      <p className="flex items-center justify-center gap-1.5 text-sm font-semibold text-amber-900">
        <AlertTriangle aria-hidden="true" className="h-4 w-4 text-amber-600" />
        <span>读取知识服务失败</span>
      </p>
      <p className="mt-1 text-xs text-amber-900/90">{error.message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-50"
      >
        <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
        <span>重试</span>
      </button>
    </div>
  );
}

export function NotFoundState({title, detail}: {title: string; detail: string}) {
  return (
    <div className="mx-auto max-w-2xl px-4 py-16 sm:px-6">
      <div className="rounded-lg border border-stone-200 bg-white p-8 text-center">
        <FileQuestion aria-hidden="true" className="mx-auto h-6 w-6 text-stone-400" />
        <h1 className="mt-3 text-lg font-bold text-stone-900">{title}</h1>
        <p className="mt-1 text-xs text-stone-500">{detail}</p>
        <NavLink
          to={listPath({q: '', kind: 'all'})}
          className="mt-5 inline-flex rounded-md bg-stone-900 px-4 py-2 text-xs font-semibold text-stone-50 hover:bg-stone-800"
        >
          返回知识列表
        </NavLink>
      </div>
    </div>
  );
}

export function Notice({title, children}: {title: string; children: ReactNode}) {
  return (
    <div className="rounded-lg border border-stone-300 bg-stone-50 p-4 text-xs text-stone-700">
      <p className="font-semibold text-stone-900">{title}</p>
      <div className="mt-1 leading-relaxed">{children}</div>
    </div>
  );
}

/** Full-document failure screen: replaces every other surface when the session is broken. */
export function GlobalFailure({
  title,
  detail,
  actionLabel,
  onAction,
}: {
  title: string;
  detail: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <main
      id="main"
      role="alert"
      className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center px-6 py-16 text-center"
    >
      <h1 className="text-lg font-bold text-stone-900">{title}</h1>
      <p className="mt-2 text-sm leading-relaxed text-stone-600">{detail}</p>
      <button
        type="button"
        onClick={onAction}
        className="mt-6 inline-flex items-center gap-1.5 rounded-md bg-stone-900 px-4 py-2 text-xs font-semibold text-stone-50 hover:bg-stone-800"
      >
        <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
        <span>{actionLabel}</span>
      </button>
    </main>
  );
}
