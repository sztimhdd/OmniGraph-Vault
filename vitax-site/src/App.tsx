import {useCallback, useEffect, useState} from 'react';

import type {KnowledgeApi, ReleaseMismatchError} from './api.ts';
import {Footer} from './components/Footer.tsx';
import {Header} from './components/Header.tsx';
import {KnowledgeDetailPage} from './components/KnowledgeDetailPage.tsx';
import {KnowledgeListPage} from './components/KnowledgeListPage.tsx';
import {GlobalFailure, NotFoundState} from './components/StateViews.tsx';
import {NavigationProvider} from './links.tsx';
import {listPath, parseRoute} from './routes.ts';
import type {Release, Route} from './types.ts';

function currentRoute(): Route {
  return parseRoute(window.location.pathname, window.location.search);
}

interface AppProps {
  api: KnowledgeApi;
  /** Confirmed by `startReader` before this component mounts. */
  release: Release;
  localArticles?: boolean;
}

export default function App({api, release, localArticles = false}: AppProps) {
  const [route, setRoute] = useState<Route>(currentRoute);
  const [sessionError, setSessionError] = useState<ReleaseMismatchError | null>(null);

  const navigate = useCallback((path: string) => {
    if (path === window.location.pathname + window.location.search) return;
    window.history.pushState(null, '', path);
    setRoute(currentRoute());
    window.scrollTo({top: 0});
  }, []);

  useEffect(() => {
    const onPopState = () => setRoute(currentRoute());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => api.onReleaseMismatch(setSessionError), [api]);

  useEffect(() => {
    const controller = new AbortController();
    const check = async () => {
      if (document.hidden) return;
      try {
        const response = await fetch('/api/release', {signal: controller.signal});
        if (!response.ok) return;
        const next: unknown = await response.json();
        if (typeof next === 'object' && next !== null && 'release_id' in next &&
            typeof next.release_id === 'string' && next.release_id && next.release_id !== release.release_id) {
          window.location.reload();
        }
      } catch { /* The pinned readable version remains until a verified update is available. */ }
    };
    const timer = window.setInterval(() => {void check();}, 60_000);
    window.addEventListener('focus', check);
    return () => {controller.abort(); window.clearInterval(timer); window.removeEventListener('focus', check);};
  }, [release.release_id]);

  if (sessionError !== null) {
    // Fail closed: one global screen replaces the header, list and any detail
    // surface, so nothing from the superseded release stays on screen.
    return (
      <div className="min-h-screen bg-[#FBFBFA] text-stone-900">
        <GlobalFailure
          title="release 在本次会话中发生变化，已停止渲染"
          detail={`${sessionError.message} 之前显示的内容可能来自另一个 release，已全部撤下。`}
          actionLabel="重新加载"
          onAction={() => window.location.reload()}
        />
      </div>
    );
  }

  return (
    <NavigationProvider value={navigate}>
      <div className="flex min-h-screen flex-col bg-[#FBFBFA] text-stone-900 selection:bg-blue-100 selection:text-blue-900">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-stone-900 focus:px-3 focus:py-2 focus:text-xs focus:font-semibold focus:text-stone-50"
        >
          跳到主要内容
        </a>
        <Header
          route={route}
          releaseId={release.release_id}
          localArticles={localArticles}
          onSearch={(query) => navigate(listPath({q: query, kind: route.name === 'list' ? route.kind : 'all'}))}
        />
        <main id="main" className="w-full flex-1">
          <RouteContent api={api} route={route} />
        </main>
        <Footer release={release} />
      </div>
    </NavigationProvider>
  );
}

function RouteContent({api, route}: {api: KnowledgeApi; route: Route}) {
  switch (route.name) {
    case 'list':
      return <KnowledgeListPage api={api} route={route} />;
    case 'article':
    case 'wiki':
      return <KnowledgeDetailPage key={`${route.name}:${route.id}`} api={api} route={route} />;
    default:
      return <NotFoundState title="未找到该页面" detail={`没有与 ${route.path} 对应的路由。`} />;
  }
}
