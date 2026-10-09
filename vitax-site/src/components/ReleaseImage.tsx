import {useState} from 'react';

interface ReleaseImageProps {
  src: string | null;
  alt: string;
  caption: string | null;
}

/**
 * Renders an image only when the release actually carries one, and reports a
 * load failure instead of showing an invented placeholder. The current public
 * read contract has no image field, so this stays dormant until it does.
 */
export function ReleaseImage({src, alt, caption}: ReleaseImageProps) {
  const [failed, setFailed] = useState(false);
  if (src === null) return null;
  if (failed) {
    return (
      <p role="status" className="rounded-md border border-stone-200 bg-stone-50 p-3 text-xs text-stone-600">
        图片无法加载。
      </p>
    );
  }
  return (
    <figure className="space-y-2">
      <img src={src} alt={alt} onError={() => setFailed(true)} loading="lazy" className="w-full rounded-lg border border-stone-200" />
      {caption !== null && <figcaption className="text-xs text-stone-500">{caption}</figcaption>}
    </figure>
  );
}
