/* Windows source CLI only: use Next's existing graceful shutdown handler. */
'use strict';
const path = require('node:path');
if (process.platform !== 'win32') throw new Error('Windows-only local entry point');
const next = path.resolve(__dirname, '../../apps/web/node_modules/next/dist/bin/next');
process.on('SIGBREAK', () => {
  if (!process.emit('SIGTERM')) process.exit(0);
});
process.argv = [process.execPath, next, ...process.argv.slice(2)];
require(next);
