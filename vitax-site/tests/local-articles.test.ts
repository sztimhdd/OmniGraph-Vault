import assert from 'node:assert/strict';
import {test} from 'node:test';

const item = {
  source: 'wechat' as const,
  record_id: 1,
  title: '原文章',
  title_translated: '中文标题',
  source_url: 'https://mp.weixin.qq.com/s/x',
  lang: 'en',
  captured_at: '2026-10-02 01:00:00',
  body_available: true,
  translation_available: true,
  rewrite_available: true,
};

test('local responses validate source, snapshot and reading-view fields', async () => {
  const {parseLibraryPage, parseLibraryDetail, sourceLink} = await import('../src/localArticles.ts');
  assert.equal(parseLibraryPage({snapshot_id: 'one', items: [item], next_offset: 20}).items[0].record_id, 1);
  const detail = parseLibraryDetail({
    snapshot_id: 'one',
    ...item,
    body: '<script>private</script>',
    body_translated: null,
    body_rewritten: '整理稿',
    translated_lang: null,
    body_html: '<p>原文</p>',
    body_translated_html: null,
    body_rewritten_html: '<p>整理稿</p>',
  });
  assert.equal(detail.body, '<script>private</script>');
  assert.equal(detail.body_html, '<p>原文</p>');
  assert.equal(detail.rewrite_available, true);
  assert.throws(() => parseLibraryPage({release_id: 'public', items: [item], next_offset: null}));
  assert.throws(() => parseLibraryPage({snapshot_id: 'one', items: [{...item, source: '../secret'}], next_offset: null}));
  assert.throws(() => parseLibraryPage({snapshot_id: 'one', items: [{...item, rewrite_available: 'yes'}], next_offset: null}));
  assert.throws(() => parseLibraryDetail({snapshot_id: 'one', ...item, body: null, body_translated: null, body_rewritten: null, translated_lang: null, body_html: 1, body_translated_html: null, body_rewritten_html: null}));
  assert.equal(sourceLink('javascript:alert(1)'), null);
  assert.equal(sourceLink('https://example.test/a'), 'https://example.test/a');
});

test('labels, reading views and return targets stay human and internal', async () => {
  const mod = await import('../src/localArticles.ts');
  assert.deepEqual(mod.availableViews(item), ['original', 'translated', 'rewrite']);
  assert.equal(mod.defaultView(item), 'rewrite');
  assert.equal(mod.defaultView({...item, rewrite_available: false}), 'original');
  assert.equal(mod.articleTitle(item), '原文章');
  assert.equal(mod.articleTitle({...item, title_translated: null}), '原文章');
  assert.equal(mod.articleStatus({body_available: true, translation_available: false, rewrite_available: true}), '原文可读 · 已有整理稿');
  assert.equal(mod.articleStatus({body_available: false, translation_available: false, rewrite_available: false}), '暂无正文');
  assert.equal(mod.sourceLabel('rss'), 'RSS');
  assert.equal(mod.sourceHost('https://mp.weixin.qq.com/s/x'), 'mp.weixin.qq.com');
  assert.equal(mod.sourceHost('javascript:alert(1)'), null);
  assert.equal(mod.displayDate(null), '采集时间未记录');
  assert.notEqual(mod.displayDate('2026-10-02 01:00:00'), '');

  const state = {q: 'TLA', source: 'rss', offset: 20, hasBody: true};
  const list = '/library?q=TLA&limit=20&offset=20&has_body=true&source=rss';
  assert.equal(mod.libraryListPath(state), list);
  assert.equal(mod.libraryItemPath({source: 'rss', record_id: 9}, state), `/library/rss/9?return=${encodeURIComponent(list)}`);

  assert.equal(mod.safeLibraryReturn('/library?q=TLA&offset=20'), '/library?q=TLA&offset=20');
  assert.equal(mod.safeLibraryReturn('//evil.test'), '/library');
  assert.equal(mod.safeLibraryReturn('https://evil.test/library'), '/library');
  assert.equal(mod.safeLibraryReturn(null), '/library');

  const detail = {snapshot_id: 'one', ...item, body: null, body_translated: null, body_rewritten: null, translated_lang: null, body_html: '<p>a</p>', body_translated_html: null, body_rewritten_html: '<p>b</p>'};
  assert.equal(mod.viewHtml(detail, 'rewrite'), '<p>b</p>');
  assert.equal(mod.viewHtml(detail, 'translated'), null);
  assert.equal(mod.viewHtml(detail, 'original'), '<p>a</p>');
  assert.equal(mod.VIEW_LABELS.rewrite, '整理稿');
});

test('article titles prefer existing Chinese and use Chinese translations only for foreign originals', async () => {
  const {articleTitle} = await import('../src/localArticles.ts');
  assert.equal(articleTitle({title: '微信中文原题', title_translated: 'English translation'}), '微信中文原题');
  assert.equal(articleTitle({title: 'Foreign original', title_translated: '中文译题'}), '中文译题');
  assert.equal(articleTitle({title: 'Foreign original', title_translated: 'Another foreign title'}), 'Foreign original');
  assert.equal(articleTitle({title: 'Foreign original', title_translated: null}), 'Foreign original');
  assert.equal(articleTitle({title: null, title_translated: '中文译题'}), '中文译题');
});
