'use strict';
// Native downloads are canceled first, then rebuilt as bounded authenticated
// requests. Neither a renderer IPC bridge nor Chromium's default file writer is
// used. The only writer is the packaged Core Python helper over anonymous stdin.
const path = require('node:path');
const fs = require('node:fs');
const {spawn} = require('node:child_process');
const {createHash} = require('node:crypto');
const {pythonPath} = require('./security.cjs');
const MAX_BYTES = 64 * 1024 * 1024;
const FETCH_TIMEOUT_MS = 60000;
const WRITE_TIMEOUT_MS = 30000;
const ID = '[A-Za-z0-9_-]{1,200}';
const WORKSPACE = new RegExp(`^/api/v1/workspaces/${ID}/exports$`);
const BOARD = new RegExp(`^/api/v1/workspaces/${ID}/boards/${ID}/exports$`);
const HYBRID = new RegExp(`^/api/v1/workspaces/${ID}/hybrid-exports$`);
const AUDIT = new RegExp(`^/api/v1/workspaces/${ID}/boards/${ID}/proposal-audit$`);

function exportRequest(value, origin) {
  try {
    const url = new URL(value);
    const own = new URL(origin);
    if (own.protocol !== 'http:' || own.hostname !== '127.0.0.1' || own.origin !== origin ||
        url.origin !== origin || url.username || url.password || url.hash || value.length > 4096) return null;
    const entries = [...url.searchParams];
    if (new Set(entries.map(([key]) => key)).size !== entries.length) return null;
    const query = Object.fromEntries(entries);
    const validRevision = () => typeof query.revision_id === 'string' && new RegExp(`^${ID}$`).test(query.revision_id);
    let extension, filename;
    if (WORKSPACE.test(url.pathname) || BOARD.test(url.pathname)) {
      const board = BOARD.test(url.pathname);
      if (entries.some(([key]) => !(board ? ['format', 'history', 'revision_id'] : ['format']).includes(key))) return null;
      if (!['csv', 'json'].includes(query.format) || (query.history !== undefined && !['true', 'false'].includes(query.history)) ||
          (query.revision_id !== undefined && !validRevision())) return null;
      extension = query.format;
      filename = `${board ? 'comparison-board' : 'evidence'}.${extension}`;
    } else if (HYBRID.test(url.pathname) && entries.length === 0) {
      extension = 'json'; filename = 'hybrid-evidence.json';
    } else if (AUDIT.test(url.pathname) && entries.length === 1 && validRevision()) {
      extension = 'json'; filename = 'cell-proposals.json';
    } else return null;
    return {url: url.href, extension, filename};
  } catch { return null; }
}

function destinationAllowed(value, {installRoot, dataRoot, extension, platform = process.platform}) {
  if (typeof value !== 'string' || !value || value.includes('\0')) return false;
  const paths = platform === 'win32' ? path.win32 : path;
  if (!paths.isAbsolute(value) || value.split(/[\\/]/).includes('..') || paths.extname(value).toLowerCase() !== `.${extension}`) return false;
  if (value.split(/[\\/]/).some(part => part.toLowerCase().endsWith('.app'))) return false;
  if (platform === 'win32' && (value.startsWith('\\\\') || value.slice(2).includes(':'))) return false;
  const target = paths.resolve(value);
  return [installRoot, dataRoot].every(root => {
    if (typeof root !== 'string' || !paths.isAbsolute(root)) return false;
    const relative = paths.relative(paths.resolve(root), target);
    return relative !== '' && (relative === '..' || relative.startsWith(`..${paths.sep}`) || paths.isAbsolute(relative));
  });
}

function abortError() { const error = new Error('Export canceled.'); error.name = 'AbortError'; return error; }
function raceAbort(promise, signal) {
  if (signal.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const cancel = () => reject(abortError());
    signal.addEventListener('abort', cancel, {once: true});
    Promise.resolve(promise).then(resolve, reject).finally(() => signal.removeEventListener('abort', cancel));
  });
}
function writerEnvironment(inherited) {
  const result = {};
  for (const key of ['SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'TMPDIR', 'HOME', 'USERPROFILE', 'LANG', 'LC_ALL', 'LC_CTYPE']) {
    if (inherited[key]) result[key] = inherited[key];
  }
  return result;
}
function requestWriter({resources, request, body = Buffer.alloc(0), signal, platform = process.platform}, dependencies = {}) {
  const spawnProcess = dependencies.spawn || spawn;
  const fileSystem = dependencies.fs || fs;
  const executable = pythonPath(resources, platform);
  const helper = path.join(resources, 'engine', 'scripts', 'desktop_native_export.py');
  // Deliberately no optional-runtime, PATH, interpreter discovery or system fallback.
  if (!fileSystem.statSync(executable).isFile() || !fileSystem.statSync(helper).isFile()) return Promise.reject(new Error('Packaged export writer unavailable.'));
  if (signal.aborted) return Promise.reject(abortError());
  const header = Buffer.from(JSON.stringify(request) + '\n');
  if (header.length > 16384 || body.length > MAX_BYTES) return Promise.reject(new Error('Export limit exceeded.'));
  return new Promise((resolve, reject) => {
    let child, completed = false, output = [] , outputSize = 0;
    const finish = (error, value) => {
      if (completed) return;
      completed = true;
      clearTimeout(timer);
      signal.removeEventListener('abort', canceled);
      if (error) { try { child?.kill(); } catch {} reject(error); } else resolve(value);
    };
    const canceled = () => finish(abortError());
    const timer = setTimeout(() => finish(new Error('Could not confirm export write.')), WRITE_TIMEOUT_MS);
    signal.addEventListener('abort', canceled, {once: true});
    try {
      child = spawnProcess(executable, ['-I', '-B', helper], {
        cwd: path.join(resources, 'engine'), env: writerEnvironment(process.env),
        windowsHide: true, stdio: ['pipe', 'pipe', 'ignore'], detached: false,
      });
      child.on('error', () => finish(new Error('Packaged export writer failed.')));
      child.stdin.on('error', () => finish(new Error('Could not confirm export write.')));
      child.stdout.on('data', chunk => {
        outputSize += chunk.length;
        if (outputSize > 32768) return finish(new Error('Invalid export writer response.'));
        output.push(chunk);
      });
      child.on('close', code => {
        if (completed) return;
        try {
          const value = JSON.parse(Buffer.concat(output).toString('utf8'));
          if (code !== 0 || !['inspected', 'written'].includes(value.status)) throw new Error();
          finish(null, value);
        } catch { finish(new Error('Export destination or write was rejected.')); }
      });
      // Paths/metadata and raw bytes travel only through this owned child's stdin.
      child.stdin.end(Buffer.concat([header, body]));
    } catch { finish(new Error('Packaged export writer failed.')); }
  });
}

async function readExport(response, request, signal) {
  if (response.status !== 200 || response.redirected || response.url && response.url !== request.url) throw new Error('Export response was not an exact successful request.');
  const type = (response.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
  if (type !== (request.extension === 'csv' ? 'text/csv' : 'application/json')) throw new Error('Unexpected export response.');
  const declared = response.headers.get('content-length');
  if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > MAX_BYTES)) throw new Error('Export exceeds the native save limit.');
  if (!response.body || typeof response.body.getReader !== 'function') throw new Error('Export stream unavailable.');
  const reader = response.body.getReader();
  const chunks = []; let size = 0;
  try {
    while (true) {
      const {done, value} = await raceAbort(reader.read(), signal);
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BYTES) throw new Error('Export exceeds the native save limit.');
      chunks.push(Buffer.from(value));
    }
    if (declared !== null && size !== Number(declared)) throw new Error('Export was incomplete.');
    return Buffer.concat(chunks, size);
  } finally {
    // Never let a stalled cancellation acknowledgement defeat the read deadline.
    try { void Promise.resolve(reader.cancel()).catch(() => {}); } catch {}
  }
}

function installNativeExports(options, dependencies = {}) {
  const {session, dialog, getWindow, origin, resources, dataRoot, installRoot, downloadsDirectory} = options;
  const runWriter = dependencies.runWriter || requestWriter;
  const platform = dependencies.platform || process.platform;
  const timeout = dependencies.fetchTimeoutMs || FETCH_TIMEOUT_MS;
  let active = null, pending = Promise.resolve(), stopped = false;
  const liveWindow = () => { const window = getWindow(); return window && !window.isDestroyed() ? window : null; };
  const handler = (event, item) => {
    // Electron's default download writer must never create a file, even for a
    // denied origin. DownloadItem may disappear immediately after this callback.
    event.preventDefault();
    let request;
    try { request = exportRequest(item.getURL(), origin); } catch { return; }
    const window = liveWindow();
    if (stopped || !request || !window) return;
    if (active) { dialog.showErrorBox('Export already in progress', 'Finish or cancel the current native save before exporting again.'); return; }
    const controller = new AbortController();
    active = controller;
    pending = (async () => {
      let timer;
      let writing = false;
      try {
        const choice = await dialog.showSaveDialog(window, {
          title: 'Save research export', defaultPath: path.join(downloadsDirectory, request.filename),
          filters: [{name: request.extension === 'csv' ? 'CSV evidence' : 'JSON evidence', extensions: [request.extension]}],
          properties: ['showOverwriteConfirmation', 'createDirectory', 'dontAddToRecent'],
        });
        if (choice.canceled || !choice.filePath || controller.signal.aborted || !liveWindow()) return;
        if (!destinationAllowed(choice.filePath, {installRoot, dataRoot, extension: request.extension, platform})) throw new Error('Choose an ordinary export file outside application and internal research folders.');
        const common = {path: choice.filePath, extension: request.extension, install_root: installRoot, data_root: dataRoot};
        const inspected = await runWriter({resources, platform, signal: controller.signal, request: {...common, operation: 'inspect'}});
        if (inspected.status !== 'inspected' || !inspected.snapshot) throw new Error('Export destination could not be checked.');
        timer = setTimeout(() => controller.abort(), timeout);
        const response = await raceAbort(session.fetch(request.url, {
          method: 'GET', credentials: 'include', redirect: 'error', cache: 'no-store',
          referrerPolicy: 'no-referrer', signal: controller.signal,
        }), controller.signal);
        const body = await readExport(response, request, controller.signal);
        clearTimeout(timer); timer = null;
        if (controller.signal.aborted || !liveWindow()) throw abortError();
        writing = true;
        const result = await runWriter({resources, platform, signal: controller.signal, body,
          request: {...common, operation: 'write', snapshot: inspected.snapshot, byte_length: body.length,
            sha256: createHash('sha256').update(body).digest('hex')}});
        if (result.status !== 'written') throw new Error('Could not confirm export write.');
        if (!stopped && liveWindow()) await dialog.showMessageBox(liveWindow(), {
          type: result.durability === 'confirmed' ? 'info' : 'warning', buttons: ['Continue research'],
          message: result.durability === 'confirmed' ? 'Research export saved' : 'Export written; disk durability not confirmed',
          detail: result.durability === 'confirmed' ? 'The selected export was saved privately. Retained research records were not changed.' : 'Check the chosen file before closing or disconnecting storage. Retained research records were not changed.',
        });
      } catch {
        if (!stopped && liveWindow()) dialog.showErrorBox('Research export was not confirmed', writing ?
          'The native write did not return confirmation. Check the chosen file before retrying. Retained research records were not changed.' :
          'The destination, export response or time/size limit was rejected. Choose an ordinary private CSV/JSON file outside application and internal research folders, then retry. No export was written; retained research records were not changed.');
      } finally { clearTimeout(timer); active = null; }
    })();
  };
  session.on('will-download', handler);
  return {
    cancelAll() { stopped = true; active?.abort(); },
    dispose() { stopped = true; active?.abort(); session.removeListener('will-download', handler); },
    whenIdle() { return pending; },
  };
}
module.exports = {installNativeExports, exportRequest, destinationAllowed, requestWriter, readExport, writerEnvironment, MAX_BYTES};
