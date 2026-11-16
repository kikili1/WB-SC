import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import { main, mergeOverride } from '../scripts/cdp_inject.mjs';

test('merge updates only selected platform and preserves unrelated data', () => {
  const current = { version: 1, other: true, overrides: {
    voice: { mac: 'Meta+D', win: 'Ctrl+D' }, search: { mac: 'Meta+F' },
  } };
  const result = mergeOverride(current, 'voice', 'Meta+J', 'mac');
  assert.equal(result.overrides.voice.mac, 'Meta+J');
  assert.equal(result.overrides.voice.win, 'Ctrl+D');
  assert.deepEqual(result.overrides.search, current.overrides.search);
  assert.equal(current.overrides.voice.mac, 'Meta+D');
  assert.equal(result.other, true);
  assert.throws(() => mergeOverride([], 'voice', 'Meta+J', 'mac'));
  assert.throws(() => mergeOverride({ overrides: { voice: 'broken' } }, 'voice', 'X', 'mac'));
  assert.throws(() => mergeOverride({}, 'toggle-window', 'X', 'mac'));
  assert.throws(() => mergeOverride({}, 'send-message', 'X', 'win'));
});

test('CDP reload/readback detects cloud override and evaluation errors', async () => {
  const savedFetch = globalThis.fetch;
  const savedSocket = globalThis.WebSocket;
  let storage, cloud = false, exception = false;
  const sockets = [];
  class Socket extends EventTarget {
    constructor() {
      super();
      sockets.push(this);
      queueMicrotask(() => this.dispatchEvent(new Event('open')));
    }
    close() { this.closed = true; }
    send(raw) {
      const message = JSON.parse(raw);
      let result = {};
      if (message.method === 'Runtime.evaluate') {
        if (exception) result = { exceptionDetails: { text: 'injected error' } };
        else {
          const value = vm.runInNewContext(message.params.expression, { localStorage: {
            getItem: () => storage, setItem: (_, value) => { storage = value; },
          } });
          result = { result: { value } };
        }
      } else if (cloud) storage = '{"version":1,"overrides":{}}';
      queueMicrotask(() => this.dispatchEvent(new MessageEvent('message', {
        data: JSON.stringify({ id: message.id, result }),
      })));
    }
  }
  globalThis.fetch = async () => ({ ok: true, json: async () => [
    { type: 'page', title: 'WorkBuddy', url: 'file:///workbuddy/index.html', webSocketDebuggerUrl: 'ws://fake' },
  ] });
  globalThis.WebSocket = Socket;
  const argv = ['node', 'cdp', '--id', 'voice', '--binding', 'Meta+J', '--platform', 'mac', '--reload'];
  try {
    storage = '{"version":1,"overrides":{"voice":{"win":"Ctrl+D"}}}';
    await main(argv);
    assert.deepEqual(JSON.parse(storage).overrides.voice, { win: 'Ctrl+D', mac: 'Meta+J' });
    cloud = true;
    await assert.rejects(main(argv), /云端覆盖/);
    cloud = false;
    exception = true;
    await assert.rejects(main(argv), /injected error/);
    assert.ok(sockets.every(socket => socket.closed));
    globalThis.WebSocket = undefined;
    await assert.rejects(main(argv), /Node.js/);
  } finally {
    globalThis.fetch = savedFetch;
    globalThis.WebSocket = savedSocket;
  }
});
