#!/usr/bin/env python3
"""Run isolated-data functional candidate. Outer OS isolation is not claimed."""
import hashlib
import http.client
import json
import os
import platform
import re
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

SOURCE = 'a54cd9acc9cca860acc0e2aabcee01f9329276c4'
STAGES = ('source', 'browser_drive', 'restart', 'browser_reopen', 'readback', 'cleanup')


class FunctionalFailure(Exception):
    pass


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_clean(source):
    return all(subprocess.run(['git','diff',*args,'--quiet','--'],cwd=source,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20).returncode == 0 for args in ([],['--cached']))


def stop(proc):
    if proc is None:
        return
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=25)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
            raise RuntimeError('owned launcher required forced stop')
    if proc.returncode != 0:
        raise RuntimeError('owned launcher did not stop normally')


def ports_free():
    sockets = []
    try:
        for port in (31881, 31882):
            s = socket.socket()
            sockets.append(s)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        for s in sockets:
            s.close()


def ready(port, route, expected):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        conn.request('GET', route)
        response = conn.getresponse()
        return response.status == 200 and json.loads(response.read(1024)) == expected
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        conn.close()


def main():
    source, candidate, result, python, node, playwright = map(Path, sys.argv[1:])
    source, candidate = source.resolve(strict=True), candidate.resolve(strict=True)
    result = result.resolve()
    stages = dict.fromkeys(STAGES, 'NOT_RUN')
    infra = candidate.parents[1]
    names = ('browser.mjs','runner.py','readback.py','validate.py','README.md')
    receipt = {'namespace':'REMOTE_WEB_FUNCTIONAL_ACCEPTANCE','scope':'NOT_STRICT_J01',
               'source_sha':SOURCE,'status':'BLOCKED','code':'SOURCE','stages':stages,
               'browser_checks':{'drive':None,'reopen':None},
               'identities':None,'artifacts':None,'tracked_source_clean':{'before':None,'after':None},
               'not_run':['back_forward','keyboard_narrow_layout','two_tab_conflict_rejected_save','unavailable_missing_evidence','models','investigations_pr25','full_matrix'],
               'outer_filesystem_network_unix_process_enforcement':'UNVERIFIED',
               'strict_j01':'NOT_RUN','pr25':'NOT_RUN', 'infra_sha':None,
               'manifest_sha256':{name:None for name in names}, 'workflow_sha256':None}
    runtime = None
    server = None
    phase = 'source'
    try:
        assert not result.exists() and result.parent.is_dir()
        actual = subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True,timeout=10).strip()
        assert actual == SOURCE
        receipt['tracked_source_clean']['before']=source_clean(source)
        assert receipt['tracked_source_clean']['before']
        infra_sha = subprocess.check_output(['git','rev-parse','HEAD'],cwd=infra,text=True,timeout=10).strip()
        assert infra_sha == os.environ['EXPECTED_INFRA_SHA'] and len(infra_sha)==40
        receipt['infra_sha']=infra_sha
        for name in names:
            receipt['manifest_sha256'][name]=hashlib.sha256((candidate/name).read_bytes()).hexdigest()
        receipt['workflow_sha256']=hashlib.sha256((infra/'.github/workflows/remote-web-functional.yml').read_bytes()).hexdigest()
        assert Path('/opt/google/chrome/chrome').is_file() and python.is_file() and node.is_file() and playwright.is_file()
        assert json.loads((playwright.parent/'package.json').read_text())['version']=='1.62.1'
        assert json.loads((playwright.parents[1]/'pnpm/package.json').read_text())['version']=='10.20.0'
        assert (source/'apps/web/.next/BUILD_ID').is_file() and ports_free()
        fixture=source/'examples/mvp/offline_microbiome_30_v1'
        combined=hashlib.sha256()
        for f in sorted(fixture.rglob('*')):
            assert not f.is_symlink()
            if f.is_file():
                combined.update(f.relative_to(fixture).as_posix().encode()+b'\0')
                combined.update(bytes.fromhex(sha(f)))
        image_os=os.environ.get('ImageOS','')
        image_version=os.environ.get('ImageVersion','')
        kernel=platform.release()
        assert all(re.fullmatch(r'[A-Za-z0-9._+-]{1,100}',x) for x in (image_os,image_version,kernel))
        receipt['identities']={'fixture_tree_sha256':combined.hexdigest(),
            'fixture_manifest_sha256':sha(fixture/'manifest.json'),
            'build_id_sha256':sha(source/'apps/web/.next/BUILD_ID'),
            'chrome_executable_sha256':sha(Path('/opt/google/chrome/chrome')),
            'python_lock_sha256':sha(source/'requirements-web-lock.txt'),
            'web_lock_sha256':sha(source/'apps/web/pnpm-lock.yaml'),
            'tools_lock_sha256':sha(playwright.parents[2]/'package-lock.json'),
            'image_os':image_os,'image_version':image_version,'kernel':kernel}
        stages['source'] = 'PASS'
        runtime = Path(tempfile.mkdtemp(prefix='remote-functional-', dir=os.environ['RUNNER_TEMP']))
        runtime.chmod(0o700)
        for directory in ('home','tmp','data','downloads'):
            (runtime/directory).mkdir(mode=0o700)
        env = {'PATH':str(node.parent)+':/usr/bin:/bin','HOME':str(runtime/'home'),
               'TMPDIR':str(runtime/'tmp'),'XDG_CACHE_HOME':str(runtime/'home/cache'),
               'LANG':'C.UTF-8','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1',
               'NEXT_TELEMETRY_DISABLED':'1','NODE_ENV':'production',
               'MVP_MAP_ENABLED':'0','MVP_SEARCH_PLANNER_ENABLED':'0','MVP_PROPOSALS_ENABLED':'0',
               'PLAYWRIGHT_MODULE':playwright.as_uri()}
        def start():
            assert ports_free()
            p = subprocess.Popen([str(python),str(source/'scripts/run_web.py'),'--data-dir',str(runtime/'data'),
                '--api-port','31881','--web-port','31882','--node',str(node),'--production'],
                cwd=source, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                deadline=time.monotonic()+100
                while time.monotonic()<deadline:
                    if p.poll() is not None: raise RuntimeError('server exited')
                    if ready(31881,'/readyz',{'ready':True}) and ready(31882,'/healthz',{'status':'ok'}): return p
                    time.sleep(.25)
                raise RuntimeError('server startup timeout')
            except BaseException:
                stop(p)
                raise
        def capture_descendants(pid):
            observed={}
            for entry in Path('/proc').iterdir():
                if not entry.name.isdigit(): continue
                try:
                    raw=(entry/'stat').read_text().rsplit(') ',1)[1].split()
                    observed[int(entry.name)]={'pid':int(entry.name),'parent':int(raw[1]),'start':raw[19]}
                except (FileNotFoundError, ProcessLookupError): pass
            owned={pid}
            for _ in range(20):
                new=owned|{i for i,x in observed.items() if x['parent'] in owned}
                if new==owned: break
                owned=new
            return [x for i,x in observed.items() if i in owned and i!=pid]
        def browser(which):
            p=subprocess.Popen([str(node),str(candidate/'browser.mjs'),str(runtime),which],cwd=source,env=env,
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                rc=p.wait(timeout=480)
            except subprocess.TimeoutExpired:
                (runtime/(which+'.timeout.owned.json')).write_text(json.dumps(capture_descendants(p.pid)))
                os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10);raise RuntimeError('browser timeout')
            gatepath=runtime/(which+'.gate.json')
            if not gatepath.exists():
                if rc==3: raise FunctionalFailure('browser journey failed')
                raise RuntimeError('browser gate blocked')
            gate=json.loads(gatepath.read_text())
            checks=('chrome_sandbox_report','renderer_namespace_distinct','renderer_extra_filter','pipe','native_confirm','cancel_false','confirm_true')
            app_checks=('app_cancel_retained','app_confirm_cleared','no_import_post') if which=='drive' else ()
            expected=set(checks)|{'version','renderer_count'}
            assert set(gate) in (expected,expected|set(app_checks))
            if set(gate)==expected|set(app_checks): assert all(gate[k] is True for k in app_checks)
            assert all(gate[k] is True for k in checks) and re.fullmatch(r'[0-9.]{1,64}',gate['version'])
            assert type(gate['renderer_count']) is int and 1 <= gate['renderer_count'] <= 256
            receipt['browser_checks'][which]=gate
            if rc==3: raise FunctionalFailure('browser journey failed')
            assert rc==0 and (runtime/(which+'.ok')).read_text()=='ok'
            assert set(gate)==expected|set(app_checks)
        server = start()
        phase='browser_drive';browser('drive');stages[phase]='PASS'
        phase='restart';stop(server);server=None
        assert ports_free()
        server=start();stages[phase]='PASS'
        phase='browser_reopen';browser('reopen');stages[phase]='PASS'
        phase='readback'
        parsed=subprocess.run([str(python),str(candidate/'readback.py'),str(source),str(runtime/'downloads/before.json'),
                        str(runtime/'downloads/after.json'),str(runtime/'downloads/before.csv'),str(runtime/'downloads/after.csv'),str(runtime/'readback.json')],env=env,cwd=source,stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
        if parsed.returncode: raise FunctionalFailure('independent readback failed')
        artifacts={name:runtime/'downloads'/name for name in ('before.json','after.json','before.csv','after.csv')}
        artifacts['readback.json']=runtime/'readback.json'
        assert all(p.is_file() and not p.is_symlink() and p.stat().st_size <= 20_000_000 for p in artifacts.values())
        for name,p in artifacts.items():
            with (result.parent/name).open('xb') as output: output.write(p.read_bytes())
        receipt['artifacts']={name:sha(p) for name,p in artifacts.items()}
        stages[phase]='PASS'
    except FunctionalFailure:
        stages[phase]='FAILED'
    except Exception:
        stages[phase]='BLOCKED'
    finally:
        try:
            stop(server)
            if runtime:
                assert ports_free()
                # Preserve runtime if any recorded owned browser process still exists.
                for inventory in runtime.glob('*.owned.json'):
                    for item in json.loads(inventory.read_text()):
                        try:
                            stat=(Path('/proc')/str(item['pid'])/'stat').read_text().rsplit(') ',1)[1].split()
                            assert stat[19] != item['start']
                        except (FileNotFoundError, ProcessLookupError): pass
                # Do not delete a profile that an owned Chrome main process still uses.
                for entry in Path('/proc').iterdir():
                    if entry.name.isdigit():
                        try:
                            args=(entry/'cmdline').read_bytes().split(b'\0')
                            assert ('--user-data-dir='+str(runtime/'profile')).encode() not in args
                        except (FileNotFoundError, ProcessLookupError):
                            pass
                shutil.rmtree(runtime)
                assert not runtime.exists()
            receipt['tracked_source_clean']['after']=source_clean(source)
            assert receipt['tracked_source_clean']['after']
            stages['cleanup']='PASS'
        except Exception:
            stages['cleanup']='BLOCKED'
        if all(stages[x]=='PASS' for x in STAGES):
            receipt['status']='PASS';receipt['code']='OK'
        else:
            failed=next((x for x in STAGES if stages[x] in ('FAILED','BLOCKED')),'source')
            receipt['status']=stages[failed]
            receipt['code']={'source':'SOURCE','browser_drive':'DRIVE','restart':'RESTART','browser_reopen':'REOPEN','readback':'READBACK','cleanup':'CLEANUP'}[failed]
        with result.open('x', encoding='utf-8') as output:
            output.write(json.dumps(receipt,sort_keys=True)+'\n')
    return {'PASS':0,'FAILED':1,'BLOCKED':2}[receipt['status']]


if __name__=='__main__':
    if not __debug__ or len(sys.argv)!=7: sys.exit(2)
    sys.exit(main())
