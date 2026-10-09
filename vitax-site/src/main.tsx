import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';

import App from './App.tsx';
import {LocalArticlesPage} from './components/LocalArticlesPage.tsx';
import {createKnowledgeApi} from './api.ts';
import {startReader} from './bootstrap.ts';
import {GlobalFailure} from './components/StateViews.tsx';
import {setListBase} from './routes.ts';
import './index.css';

const element = document.getElementById('root');
if (element === null) {
  throw new Error('reader requires a #root container');
}
const container: HTMLElement = element;

const api = createKnowledgeApi((input, init) => window.fetch(input, init));

async function boot() {
  const response = await fetch('/api/capabilities');
  if (!response.ok) throw new Error('无法确认读取服务');
  const capabilities = await response.json();
  if (typeof capabilities.public_knowledge !== 'boolean' || typeof capabilities.local_articles !== 'boolean') throw new Error('读取服务能力无效');
  const path = window.location.pathname;
  // With an article library configured the library is the home route; the
  // knowledge list keeps its own `/knowledge` entry. Public-only keeps `/`.
  const libraryRoute = capabilities.local_articles && (path === '/' || path === '/index.html' || path === '/library' || path.startsWith('/library/'));
  if (libraryRoute || !capabilities.public_knowledge) {
    if (!capabilities.local_articles) throw new Error('本地文章库未启用');
    setListBase(capabilities.public_knowledge ? '/knowledge' : '/');
    container.replaceChildren();
    createRoot(container).render(<StrictMode><LocalArticlesPage publicKnowledge={capabilities.public_knowledge} /></StrictMode>);
    return;
  }
  setListBase(capabilities.local_articles ? '/knowledge' : '/');
  await startReader(api, {
  clearPrerendered: () => container.replaceChildren(),
  renderReader: (release) =>
    createRoot(container).render(
      <StrictMode>
        <App api={api} release={release} localArticles={capabilities.local_articles} />
      </StrictMode>,
    ),
  renderBootstrapFailure: (error) =>
    createRoot(container).render(
      <StrictMode>
        <GlobalFailure
          title="无法确认公开 release"
          detail={`${error.message} 请确认读取服务正常后重新加载。`}
          actionLabel="重新加载"
          onAction={() => window.location.reload()}
        />
      </StrictMode>,
    ),
});
}
void boot().catch(error => {
  container.replaceChildren();
  createRoot(container).render(<GlobalFailure title="无法读取 VitaX" detail={error instanceof Error ? error.message : '读取失败'} actionLabel="重新加载" onAction={() => window.location.reload()} />);
});
