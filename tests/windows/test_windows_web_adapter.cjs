/* Signal-bridge contract only. Native Windows lifecycle is a separate CI gate. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {EventEmitter}=require('node:events');
const {test}=require('node:test');
const filename=path.resolve(__dirname,'../../src/platform_support/windows_web.cjs');
const source=fs.readFileSync(filename,'utf8');

function load(existingHandler){
  const process=new EventEmitter(),exits=[],loaded=[];
  Object.assign(process,{platform:'win32',execPath:'node-fixture.exe',
    argv:['node-fixture.exe',filename,'start','--hostname','127.0.0.1','--port','43123'],
    exit:code=>exits.push(code)});
  const expected=path.resolve(path.dirname(filename),'../../apps/web/node_modules/next/dist/bin/next');
  vm.runInNewContext(source,{process,__dirname:path.dirname(filename),require:specifier=>{
    if(specifier==='node:path')return path;
    assert.equal(specifier,expected);loaded.push(specifier);
    if(existingHandler)process.on('SIGTERM',signal=>existingHandler(signal,process));
    return {};
  }},{filename});
  return {process,exits,loaded,expected};
}

test('SIGBREAK delegates the explicit signal to existing Next cleanup and preserves its status',()=>{
  const received=[];
  const fixture=load((signal,process)=>{received.push(signal);process.exit(signal==='SIGTERM'?143:128);});
  assert.equal(fixture.loaded.length,1);
  assert.deepEqual(Array.from(fixture.process.argv),['node-fixture.exe',fixture.expected,'start','--hostname','127.0.0.1','--port','43123']);
  fixture.process.emit('SIGBREAK');
  assert.deepEqual(received,['SIGTERM']);
  assert.deepEqual(fixture.exits,[143]);
});

test('bridge neither preemptively exits nor replaces an asynchronous cleanup handler',()=>{
  let cleanup;
  const fixture=load((signal,process)=>{assert.equal(signal,'SIGTERM');cleanup=()=>process.exit(143);});
  fixture.process.emit('SIGBREAK');
  assert.deepEqual(fixture.exits,[]);
  cleanup();assert.deepEqual(fixture.exits,[143]);
});
