import assert from 'node:assert/strict';
import test from 'node:test';

import {startReader} from '../src/bootstrap.ts';
import {NetworkError} from '../src/api.ts';
import type {Release} from '../src/types.ts';

const RELEASE: Release = {release_id: 'release-test', published_at: '2026-09-09T12:00:00Z'};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return {promise, resolve, reject};
}

function mount(events: string[], captured: {error?: Error; release?: Release}) {
  return {
    clearPrerendered: () => events.push('clear'),
    renderReader: (release: Release) => {
      captured.release = release;
      events.push('renderReader');
    },
    renderBootstrapFailure: (error: Error) => {
      captured.error = error;
      events.push('renderBootstrapFailure');
    },
  };
}

test('prerendered markup stays untouched while the release is unconfirmed', async () => {
  const events: string[] = [];
  const captured: {error?: Error; release?: Release} = {};
  const gate = deferred<Release>();
  const pending = startReader({bootstrap: () => gate.promise}, mount(events, captured));

  await Promise.resolve();
  await Promise.resolve();
  assert.deepEqual(events, [], 'nothing may be cleared or rendered before the release is known');

  gate.resolve(RELEASE);
  assert.equal(await pending, 'ready');
  assert.deepEqual(events, ['clear', 'renderReader'], 'replacement happens only after a confirmed release');
  assert.deepEqual(captured.release, RELEASE);
  assert.equal(captured.error, undefined);
});

test('a failed bootstrap replaces the markup with one bounded global error', async () => {
  const events: string[] = [];
  const captured: {error?: Error; release?: Release} = {};
  const failure = new NetworkError('无法连接知识服务，请确认本地读取服务正在运行。');
  const status = await startReader({bootstrap: () => Promise.reject(failure)}, mount(events, captured));

  assert.equal(status, 'failed');
  assert.deepEqual(events, ['clear', 'renderBootstrapFailure']);
  assert.equal(captured.error, failure);
  assert.equal(captured.release, undefined, 'the reader must not mount without a release');
});

test('a non-error bootstrap rejection is still reported as an Error', async () => {
  const events: string[] = [];
  const captured: {error?: Error; release?: Release} = {};
  const status = await startReader({bootstrap: () => Promise.reject('offline')}, mount(events, captured));

  assert.equal(status, 'failed');
  assert.ok(captured.error instanceof Error);
  assert.equal(captured.error?.message, 'offline');
});

test('the release read is attempted exactly once before anything is rendered', async () => {
  let bootstraps = 0;
  const events: string[] = [];
  const captured: {error?: Error; release?: Release} = {};
  await startReader(
    {
      bootstrap: async () => {
        bootstraps += 1;
        return RELEASE;
      },
    },
    mount(events, captured),
  );
  assert.equal(bootstraps, 1);
  assert.deepEqual(events, ['clear', 'renderReader']);
});
