"""The existing body entrypoint reports partial work without losing good rows."""
import asyncio
import json
import sqlite3

from enrichment import rss_rescrape_bodies as worker


def test_body_entrypoint_reports_partial_and_empty_run(tmp_path, monkeypatch, capsys):
    db = tmp_path / "rss.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE rss_articles(id INTEGER PRIMARY KEY,url TEXT,body TEXT,layer1_verdict TEXT)")
        conn.executemany("INSERT INTO rss_articles VALUES(?,?,NULL,'candidate')", [(1, 'https://synthetic/good'), (2, 'https://synthetic/bad')])
    calls = []
    async def scrape(url):
        calls.append(url)
        return 'synthetic original body' if url.endswith('good') else None
    async def no_sleep(_):
        pass
    monkeypatch.setattr(worker, 'DB_PATH', db)
    monkeypatch.setattr(worker, 'rescrape_one', scrape)
    monkeypatch.setattr(worker.asyncio, 'sleep', no_sleep)
    assert asyncio.run(worker.main()) == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary == {'status': 'partial', 'attempted': 2, 'rescued': 1, 'failed': 1, 'remaining': 1}
    assert len(calls) == 2 and len(set(calls)) == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT body FROM rss_articles WHERE id=1').fetchone()[0] == 'synthetic original body'
        conn.execute('UPDATE rss_articles SET body=? WHERE id=2', ('already present',))
    assert asyncio.run(worker.main()) == 0
    assert json.loads(capsys.readouterr().out) == {'status': 'ok', 'attempted': 0, 'rescued': 0, 'failed': 0, 'remaining': 0}
    assert len(calls) == 2
