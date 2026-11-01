#!/usr/bin/env python3
"""Validate the public-artifact allowlist, identities and readback hashes."""
import base64
import gzip
import hashlib
import os
import subprocess
import tempfile
import json
from pathlib import Path
import re
import sys

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def strict_loads(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


try:
    assert __debug__ and len(sys.argv)==3
    path=Path(sys.argv[1]); folder=path.parent; source=Path(sys.argv[2]).resolve(strict=True)
    def clean():
        return all(subprocess.run(['git','diff',*args,'--quiet','--'],cwd=source,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20).returncode==0 for args in ([],['--cached']))
    assert clean()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True,timeout=10).strip()=='a54cd9acc9cca860acc0e2aabcee01f9329276c4'
    assert path.name=='receipt.json' and not path.is_symlink() and path.is_file() and path.stat().st_size<16384
    v=strict_loads(path.read_text())
    keys={'namespace','scope','source_sha','status','code','stages','browser_checks','identities','artifacts','tracked_source_clean','not_run','outer_filesystem_network_unix_process_enforcement','strict_j01','pr25','infra_sha','manifest_sha256','workflow_sha256'}
    assert set(v)==keys
    assert v['namespace']=='REMOTE_WEB_FUNCTIONAL_ACCEPTANCE' and v['scope']=='NOT_STRICT_J01'
    assert v['source_sha']=='a54cd9acc9cca860acc0e2aabcee01f9329276c4'
    assert v['outer_filesystem_network_unix_process_enforcement']=='UNVERIFIED' and v['strict_j01']=='NOT_RUN' and v['pr25']=='NOT_RUN'
    assert v['not_run']==['back_forward','keyboard_narrow_layout','two_tab_conflict_rejected_save','unavailable_missing_evidence','models','investigations_pr25','full_matrix']
    assert set(v['tracked_source_clean'])=={'before','after'} and all(x in (True,False,None) for x in v['tracked_source_clean'].values())
    assert v['status'] in ('PASS','FAILED','BLOCKED')
    assert v['code'] in ('OK','SOURCE','DRIVE','RESTART','REOPEN','READBACK','CLEANUP')
    assert set(v['browser_checks'])=={'drive','reopen'}
    checks={'chrome_sandbox_report','renderer_namespace_distinct','renderer_extra_filter','pipe','native_confirm','cancel_false','confirm_true'}
    for phase,gate in v['browser_checks'].items():
        if gate is not None:
            app={'app_cancel_retained','app_confirm_cleared','no_import_post'} if phase=='drive' else set()
            basic=checks|{'version','renderer_count'}
            assert set(gate) in (basic,basic|app)
            assert all(gate[k] is True for k in set(gate)&(checks|app)) and re.fullmatch('[0-9.]{1,64}',gate['version'])
            assert type(gate['renderer_count']) is int and 1<=gate['renderer_count']<=256
    assert set(v['stages'])=={'source','browser_drive','restart','browser_reopen','readback','cleanup'}
    assert all(x in ('PASS','FAILED','BLOCKED','NOT_RUN') for x in v['stages'].values())
    assert set(v['manifest_sha256'])=={'browser.mjs','runner.py','readback.py','validate.py','README.md'}
    assert v['infra_sha'] is None or re.fullmatch('[0-9a-f]{40}',v['infra_sha'])
    for h in [v['workflow_sha256'],*v['manifest_sha256'].values()]: assert h is None or re.fullmatch('[0-9a-f]{64}',h)
    if v['identities'] is not None:
        ids=v['identities']; hashes={'fixture_tree_sha256','fixture_manifest_sha256','build_id_sha256','chrome_executable_sha256','python_lock_sha256','web_lock_sha256','tools_lock_sha256'}
        assert set(ids)==hashes|{'image_os','image_version','kernel'}
        assert all(re.fullmatch('[0-9a-f]{64}',ids[k]) for k in hashes)
        assert all(re.fullmatch('[A-Za-z0-9._+-]{1,100}',ids[k]) for k in ('image_os','image_version','kernel'))
    allowed={'receipt.json'}
    if v['artifacts'] is not None:
        a=v['artifacts'];assert set(a)=={'before.json','after.json','before.csv','after.csv','readback.json'}
        allowed |= set(a)
        for name,digest in a.items():
            f=folder/name;assert not f.is_symlink() and f.is_file() and f.stat().st_size<=20_000_000
            assert re.fullmatch('[0-9a-f]{64}',digest) and hashlib.sha256(f.read_bytes()).hexdigest()==digest
        # Independently reject duplicate keys at every depth in both raw exports.
        for name in ('before.json','after.json'):
            strict_loads((folder/name).read_bytes())
        proof=strict_loads((folder/'readback.json').read_text())
        assert set(proof)=={'schema','status','before_sha256','after_sha256','before_csv_sha256','after_csv_sha256','pmid','field','submitted_revisions','table_cells','source_ranges_valid','csv_parity'}
        assert proof['schema']=='remote-functional-readback-v1' and proof['status']=='PASS'
        assert proof['before_sha256']==a['before.json'] and proof['after_sha256']==a['after.json'] and a['before.json']==a['after.json']
        assert proof['before_csv_sha256']==a['before.csv'] and proof['after_csv_sha256']==a['after.csv'] and a['before.csv']==a['after.csv'] and proof['csv_parity'] is True
        assert proof['pmid']=='42051515' and proof['field']=='population' and proof['submitted_revisions']==1 and proof['table_cells']==9 and proof['source_ranges_valid'] is True
    assert {p.name for p in folder.iterdir()}==allowed
    if v['status']=='PASS':
        assert v['code']=='OK' and all(x=='PASS' for x in v['stages'].values())
        assert all(x is True for x in v['tracked_source_clean'].values())
        assert all(v['browser_checks'].values()) and v['identities'] and v['artifacts']
        assert all(v['browser_checks']['drive'].get(k) is True for k in ('app_cancel_retained','app_confirm_cleared','no_import_post'))
        assert v['infra_sha'] and v['workflow_sha256'] and all(v['manifest_sha256'].values())
    else:
        assert v['code']!='OK' and v['status'] in v['stages'].values()
        raise ValueError('no bundle on incomplete run')
    # Re-run the independent parser after cleanup, in a fresh process. No
    # output is emitted until every check, source identity and size gate passes.
    with tempfile.TemporaryDirectory(prefix='functional-readback-') as temp:
        env={'PATH':'/usr/bin:/bin','HOME':temp,'TMPDIR':temp,'LANG':'C.UTF-8',
             'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
        proof_copy=Path(temp)/'proof.json'
        subprocess.run([sys.executable,str(Path(__file__).resolve().parent/'readback.py'),str(source),
                        str(folder/'before.json'),str(folder/'after.json'),str(folder/'before.csv'),str(folder/'after.csv'),str(proof_copy)],
                       cwd=source,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,timeout=90,check=True)
        assert strict_loads(proof_copy.read_text())==proof
    assert clean()
    files={name:base64.b64encode((folder/name).read_bytes()).decode('ascii') for name in sorted(allowed)}
    raw=json.dumps({'schema':'remote-functional-bundle-v1','files':files},sort_keys=True,separators=(',',':')).encode()
    assert len(raw)<=60_000_000
    compressed=gzip.compress(raw,compresslevel=9,mtime=0)
    assert len(compressed)<=1_048_576
    encoded=base64.b64encode(compressed).decode('ascii')
    chunks=[encoded[i:i+4096] for i in range(0,len(encoded),4096)]
    header='REMOTE_FUNCTIONAL_BUNDLE_V1 BEGIN compressed_bytes=%d raw_bytes=%d compressed_sha256=%s raw_sha256=%s chunks=%d' % (len(compressed),len(raw),hashlib.sha256(compressed).hexdigest(),hashlib.sha256(raw).hexdigest(),len(chunks))
    lines=[header]+['REMOTE_FUNCTIONAL_BUNDLE_CHUNK %d/%d %s' % (i+1,len(chunks),chunk) for i,chunk in enumerate(chunks)]+['REMOTE_FUNCTIONAL_BUNDLE_V1 END']
    sys.stdout.write('\n'.join(lines)+'\n')
except Exception:
    print('REMOTE_FUNCTIONAL_NO_BUNDLE')
    sys.exit(2)
