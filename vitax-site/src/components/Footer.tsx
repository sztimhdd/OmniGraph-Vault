import type {Release} from '../types.ts';

/** Release provenance only: no counters, no feedback or review actions. */
export function Footer({release}: {release: Release | null}) {
  return (
    <footer className="mt-12 border-t border-stone-200 bg-stone-100 px-4 py-8 text-xs text-stone-600 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-2">
        <p className="font-semibold text-stone-800">VitaX 公开知识阅读</p>
        <p>
          本站只展示当前 release 中标记为公开的知识与证据；正文证据指向原始来源，请以来源为准。
        </p>
        <p className="text-stone-500">
          {release === null ? (
            '尚未读取到 release 元数据。'
          ) : (
            <>
              release <code className="font-mono">{release.release_id}</code> · 发布于{' '}
              <time dateTime={release.published_at}>{release.published_at}</time>
            </>
          )}
        </p>
      </div>
    </footer>
  );
}
