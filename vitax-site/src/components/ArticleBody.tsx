import {useEffect, useRef} from 'react';

/** A broken image becomes a visible note instead of an empty placeholder. */
function missingImage(alt: string | null): HTMLElement {
  const note = document.createElement('p');
  note.className = 'article-image-missing';
  note.textContent = alt ? `图片无法加载：${alt}` : '图片无法加载。';
  return note;
}

/**
 * Render API-produced, server-sanitized article HTML. The markup is already
 * rebuilt from an allowlist, so only the image error hook is added here.
 */
export function ArticleBody({html}: {html: string}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (node === null) return;
    const images = Array.from(node.querySelectorAll('img'));
    const onError = (event: Event) => {
      const image = event.currentTarget as HTMLImageElement;
      image.replaceWith(missingImage(image.getAttribute('alt')));
    };
    images.forEach((image) => image.addEventListener('error', onError));
    return () => images.forEach((image) => image.removeEventListener('error', onError));
  }, [html]);
  return <div ref={ref} className="article-body break-words" data-testid="article-body" dangerouslySetInnerHTML={{__html: html}} />;
}
