'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {PassThrough} = require('node:stream');
const {installNativeExports, exportRequest, destinationAllowed, requestWriter, readExport, writerEnvironment, MAX_BYTES} = require('../../apps/desktop/native-exports.cjs');
const origin = 'http://127.0.0.1:43000';
const base = origin + '/api/v1/workspaces/workspace-1';
const options = {origin, resources: '/Applications/Test.app/Contents/Resources', dataRoot: '/private/data', installRoot: '/Applications/Test.app', downloadsDirectory: '/private/downloads'};
function fixture(extra = {}) {
  const session = new EventEmitter();
  const calls = [];
  const currentWindow = {isDestroyed: () => false};
  const dialog = {
    async showSaveDialog(window, settings) { calls.push(['dialog', window, settings]); return {canceled: false, filePath: '/private/downloads/evidence.csv'}; },
    showErrorBox(...args) { calls.push(['error', ...args]); },
    async showMessageBox(...args) { calls.push(['message', ...args]); },
  };
  session.fetch = async (url, settings) => { calls.push(['fetch', url, settings]); return new Response('source,value\npublic,manual\n', {status: 200, headers: {'content-type': 'text/csv'}}); };
  const runWriter = async input => { calls.push(['writer', input]); return input.request.operation === 'inspect' ? {status: 'inspected', snapshot: {target: null}} : {status: 'written', durability: 'confirmed'}; };
  const controller = installNativeExports({...options, session, dialog, getWindow: () => currentWindow, ...extra.options}, {runWriter, ...extra.dependencies});
  function download(url = base + '/exports?format=csv') {
    const event = {preventDefault() { calls.push(['prevent']); }};
    session.emit('will-download', event, {getURL: () => url, getFilename() { throw Error('Untrusted browser filename must never be used.'); }});
    return controller.whenIdle();
  }
  return {session, dialog, calls, currentWindow, controller, download};
}

test('exact research routes only; unknown paths and query variants are denied', () => {
  for (const [suffix, filename] of [
    ['/exports?format=csv', 'evidence.csv'], ['/exports?format=json', 'evidence.json'],
    ['/boards/b-1/exports?format=csv&history=true&revision_id=r-1', 'comparison-board.csv'],
    ['/hybrid-exports', 'hybrid-evidence.json'], ['/boards/b-1/proposal-audit?revision_id=r-1', 'cell-proposals.json'],
  ]) assert.equal(exportRequest(base + suffix, origin).filename, filename);
  for (const url of [
    'https://evil.test/file.csv', origin + '/api/v1/session', base + '/exports',
    base + '/exports?format=csv&format=json', base + '/exports?format=csv&token=secret',
    base + '/exports?format=csv#private', base + '/exports?format=html',
    base + '/boards/b/exports?format=json&history=1', base + '/hybrid-exports?format=json',
    base + '/boards/b/proposal-audit?revision_id=x/y', base + '/boards/b/proposal-audit',
    origin.replace('127.0.0.1', 'localhost') + '/api/v1/workspaces/w/exports?format=csv',
    'http://person:secret@127.0.0.1:43000/api/v1/workspaces/w/exports?format=csv',
    origin + '/api/v1/workspaces/w%2Fz/exports?format=csv',
  ]) assert.equal(exportRequest(url, origin), null, url);
});

test('native download is canceled synchronously before any chooser or writer and uses real SaveDialog contract', async () => {
  const f = fixture();
  const pending = f.download();
  assert.equal(f.calls[0][0], 'prevent');
  assert.equal(f.calls[1][0], 'dialog');
  await pending;
  assert.equal(f.calls[1][1], f.currentWindow);
  assert.deepEqual(f.calls[1][2].properties, ['showOverwriteConfirmation', 'createDirectory', 'dontAddToRecent']);
  assert.equal(f.calls[1][2].defaultPath, '/private/downloads/evidence.csv');
  assert.deepEqual(f.calls.map(call => call[0]), ['prevent', 'dialog', 'writer', 'fetch', 'writer', 'message']);
  const fetch = f.calls.find(call => call[0] === 'fetch');
  assert.equal(fetch[2].credentials, 'include');
  assert.equal(fetch[2].redirect, 'error');
  assert.equal(fetch[2].method, 'GET');
  assert.equal(fetch[2].referrerPolicy, 'no-referrer');
  assert.equal(fetch[2].headers, undefined);
  const write = f.calls.filter(call => call[0] === 'writer')[1][1];
  assert.equal(write.body.toString(), 'source,value\npublic,manual\n');
  assert.equal(write.request.byte_length, write.body.length);
  assert.equal(write.request.sha256.length, 64);
});

test('foreign download is canceled with no chooser, request or write', async () => {
  const f = fixture(); await f.download('https://evil.test/unknown.csv');
  assert.deepEqual(f.calls, [['prevent']]);
});
test('canceling SaveDialog causes no fetch or helper and no error', async () => {
  const f = fixture(); f.dialog.showSaveDialog = async () => ({canceled: true});
  await f.download(); assert.deepEqual(f.calls, [['prevent']]);
});
test('window is obtained at event time, not early initialization', async () => {
  let current = null;
  const f = fixture({options: {getWindow: () => current}});
  current = f.currentWindow;
  await f.download(); assert.equal(f.calls[1][1], current);
});
test('destination rejects any app bundle, internal data, install path, unsafe extension and Windows path devices', () => {
  for (const value of ['/private/Other.APP/evidence.csv', '/private/data/evidence.csv', '/private/data/sub/out.csv', '/Applications/Test.app/out.csv', '/private/out.json', '/private/../out.csv']) {
    assert.equal(destinationAllowed(value, {...options, extension: 'csv'}), false, value);
  }
  assert.equal(destinationAllowed('/private/downloads/evidence.csv', {...options, extension: 'csv'}), true);
  const win = {platform: 'win32', extension: 'json', installRoot: 'C:\\Users\\Fixture\\Programs\\Literature', dataRoot: 'C:\\Users\\Fixture\\Data'};
  for (const value of ['C:\\Users\\Fixture\\Programs\\Literature\\out.json', 'c:\\users\\fixture\\data\\out.json', '\\\\server\\share\\out.json', 'C:\\out.json:stream', 'C:\\Other.app\\out.json']) assert.equal(destinationAllowed(value, win), false, value);
  assert.equal(destinationAllowed('C:\\Users\\Fixture\\Downloads\\out.json', win), true);
});
test('internal destination is rejected before a fetch or helper', async () => {
  const f = fixture(); f.dialog.showSaveDialog = async () => ({filePath: '/private/data/output.csv'});
  await f.download(); assert.deepEqual(f.calls.map(call => call[0]), ['prevent', 'error']);
});
test('authoritative helper rejection prevents managed fetch and never invokes write', async () => {
  const f = fixture({dependencies: {runWriter: async () => {throw Error('synthetic unsafe owner');}}});
  await f.download(); assert.equal(f.calls.some(call => call[0] === 'fetch'), false);
  assert.equal(f.calls.filter(call => call[0] === 'error').length, 1);
});
test('failed, redirected, mismatched and incomplete responses cannot reach writer', async () => {
  for (const response of [
    new Response('denied', {status: 403, headers: {'content-type': 'text/csv'}}),
    new Response('<html>not CSV</html>', {headers: {'content-type': 'text/html'}}),
    new Response('short', {headers: {'content-type': 'text/csv', 'content-length': '12'}}),
    new Response('large', {headers: {'content-type': 'text/csv', 'content-length': String(MAX_BYTES + 1)}}),
    {status: 200, redirected: true},
  ]) {
    const f = fixture(); f.session.fetch = async () => response;
    await f.download(); assert.equal(f.calls.filter(call => call[0] === 'writer').length, 1);
    assert.equal(f.calls.filter(call => call[0] === 'error').length, 1);
  }
});
test('stream overflow is rejected without truncating or writing a prefix', async () => {
  const response = new Response(new ReadableStream({start(controller) {controller.enqueue(new Uint8Array(MAX_BYTES)); controller.enqueue(new Uint8Array(1)); controller.close();}}), {headers: {'content-type': 'text/csv'}});
  await assert.rejects(readExport(response, {url: base + '/exports?format=csv', extension: 'csv'}, new AbortController().signal));
});
test('request timeout and cancellation are bounded with no save', async () => {
  const f = fixture({dependencies: {fetchTimeoutMs: 15}});
  f.session.fetch = () => new Promise(() => {});
  await f.download(); assert.equal(f.calls.filter(call => call[0] === 'writer').length, 1);
  assert.equal(f.calls.filter(call => call[0] === 'error').length, 1);
  const g = fixture(); g.session.fetch = () => new Promise(() => {});
  const waiting = g.download(); await new Promise(resolve => setImmediate(resolve));
  g.controller.cancelAll(); await waiting;
  assert.equal(g.calls.filter(call => call[0] === 'writer').length, 1);
  assert.equal(g.calls.some(call => call[0] === 'error'), false);
});
test('one native export at a time and dispose removes listener', async () => {
  const f = fixture(); let finish;
  f.dialog.showSaveDialog = () => new Promise(resolve => {finish = resolve;});
  const first = f.download(); void f.download();
  assert.equal(f.calls.filter(call => call[0] === 'error').length, 1);
  finish({canceled: true}); await first;
  f.controller.dispose(); assert.equal(f.session.listenerCount('will-download'), 0);
});
test('writer uses only bundled Core Python and anonymous stdin, with no provider environment', async () => {
  const calls = [];
  const fakeSpawn = (executable, args, settings) => {
    calls.push({executable, args, settings});
    const child = new EventEmitter(); child.stdin = new PassThrough(); child.stdout = new PassThrough(); child.kill = () => {};
    const input = []; child.stdin.on('data', chunk => input.push(chunk));
    child.stdin.on('finish', () => {calls[0].input = Buffer.concat(input); child.stdout.write('{"status":"written","durability":"confirmed"}'); child.emit('close', 0);});
    return child;
  };
  const body = Buffer.from('private export bytes');
  await requestWriter({resources: options.resources, request: {operation: 'write', path: '/private/selected.csv'}, body, signal: new AbortController().signal}, {spawn: fakeSpawn, fs: {statSync: () => ({isFile: () => true})}});
  assert.equal(calls[0].executable, options.resources + '/python/bin/python3.12');
  assert.deepEqual(calls[0].args, ['-I', '-B', options.resources + '/engine/scripts/desktop_native_export.py']);
  assert.equal(calls[0].settings.stdio[2], 'ignore');
  assert.equal(calls[0].args.some(value => value.includes('selected') || value.includes('private export')), false);
  assert.equal(calls[0].input.subarray(calls[0].input.indexOf(10) + 1).toString(), body.toString());
  const clean = writerEnvironment({HOME: '/private/home',PATH: '/developer',PYTHONPATH: 'unsafe',OPENAI_API_KEY: 'synthetic',NODE_OPTIONS: 'unsafe',HTTPS_PROXY: 'unsafe'});
  assert.deepEqual(clean, {HOME: '/private/home'});
});
test('uncertain atomic-write reply does not claim the file was unchanged', async () => {
  let count = 0;
  const f = fixture({dependencies: {runWriter: async () => ++count === 1 ? {status: 'inspected', snapshot: {target: null}} : Promise.reject(Error('synthetic terminated writer'))}});
  await f.download(); const message = f.calls.find(call => call[0] === 'error')[2];
  assert.match(message, /Check the chosen file/); assert.doesNotMatch(message, /No export was written/);
});
