import {Search} from 'lucide-react';
import {useEffect, useState} from 'react';

import {NavLink} from '../links.tsx';
import type {Route} from '../types.ts';

interface HeaderProps {
  route: Route;
  releaseId: string | null;
  localArticles?: boolean;
  onSearch: (query: string) => void;
}

export function Header({route, releaseId, onSearch, localArticles = false}: HeaderProps) {
  const routeQuery = route.name === 'list' ? route.q : '';
  const [query, setQuery] = useState(routeQuery);
  const libraryHref = route.name === 'list' && route.q !== '' ? `/library?q=${encodeURIComponent(route.q)}` : '/library';

  useEffect(() => {
    setQuery(routeQuery);
  }, [routeQuery]);

  return (
    <header className="sticky top-0 z-40 border-b border-stone-200/80 bg-[#FBFBFA]">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <div className="flex items-center justify-between gap-4">
          {localArticles ? <a href="/" className="flex items-baseline gap-2 py-1">
            <span className="text-xl font-extrabold tracking-tight text-stone-900">
              Vita<span className="text-blue-600">X</span>
            </span>
            <span className="rounded bg-stone-200/70 px-1.5 py-0.5 text-[11px] font-semibold text-stone-700">
              公开知识阅读
            </span>
          </a> : <NavLink to="/" className="flex items-baseline gap-2 py-1">
            <span className="text-xl font-extrabold tracking-tight text-stone-900">
              Vita<span className="text-blue-600">X</span>
            </span>
            <span className="rounded bg-stone-200/70 px-1.5 py-0.5 text-[11px] font-semibold text-stone-700">
              公开知识阅读
            </span>
          </NavLink>}
          {localArticles ? <a href={libraryHref} className="text-sm font-semibold text-blue-700">文章库</a> : null}
          {releaseId !== null && (
            <span className="rounded border border-stone-200 bg-white px-2 py-0.5 font-mono text-[11px] text-stone-600">
              release {releaseId}
            </span>
          )}
        </div>

        <form
          role="search"
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            onSearch(query);
          }}
        >
          <label htmlFor="knowledge-search" className="sr-only">
            检索知识条目
          </label>
          <div className="relative flex-1 lg:w-72">
            <Search aria-hidden="true" className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-stone-400" />
            <input
              id="knowledge-search"
              name="q"
              type="search"
              autoComplete="off"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="检索公开知识标题或正文"
              className="w-full rounded-md border border-stone-200 bg-white py-1.5 pl-8 pr-3 text-xs text-stone-900 placeholder-stone-400 focus-visible:border-blue-600"
            />
          </div>
          <button
            type="submit"
            className="rounded-md bg-stone-900 px-3 py-1.5 text-xs font-semibold text-stone-50 hover:bg-stone-800"
          >
            检索
          </button>
        </form>
      </div>
    </header>
  );
}
