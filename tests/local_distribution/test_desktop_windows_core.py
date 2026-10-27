"""Synthetic build-only pruning fixtures; never execute Windows code."""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path

import pytest
from scripts import desktop_windows_core as core


def put(root, name, data):
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path


def entry(data):
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def snapshot(root):
    return {p.relative_to(root).as_posix():('link',str(p.readlink())) if p.is_symlink() else ('file',p.read_bytes())
            for p in root.rglob('*') if p.is_file() or p.is_symlink()}


def inputs(tmp_path):
    app=tmp_path/'app';resources=app/'resources';resources.mkdir(parents=True)
    omitted={};protected={}
    for index,prefix in enumerate(core.ALLOWED_DIRECTORIES):
        name=prefix+'/component.pyd';data=f'Public optional fixture {index}'.encode()
        put(app,name,data);omitted[name]=entry(data)
    for name,data in {
        core.SITE+'pywin32.pth':b'win32\nwin32\\lib\npythonwin\nimport pywin32_bootstrap\n',
        core.SITE+'win32/lib/pywin32_bootstrap.py':b'# public synthetic bootstrap\n',
        core.SITE+'win32/_win32sysloader.pyd':b'public synthetic loader',
        core.SITE+'pywin32-312.dist-info/licenses/win32/License.txt':b'Public synthetic license\n',
        'resources/python/python.exe':b'public synthetic Python runtime',
    }.items():
        put(app,name,data);protected[name]=entry(data)
    put(app,core.SITE+'unrelated.py',b'# Retain every unrelated byte\n')
    record_files={p.relative_to(app).as_posix():entry(p.read_bytes()) for p in (app/core.SITE).rglob('*') if p.is_file()}
    record_path=core.SITE+'pywin32-312.dist-info/RECORD'
    removed=['../../bin/pywin32_postinstall','../../bin/pywin32_postinstall.py','../../bin/pywin32_testall','../../bin/pywin32_testall.py']
    rows=[]
    for name,row in record_files.items():
        encoded=base64.urlsafe_b64encode(bytes.fromhex(row['sha256'])).decode().rstrip('=')
        rows.append([name.removeprefix(core.SITE),'sha256='+encoded,str(row['bytes'])])
    rows += [[name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(b'entrypoint').digest()).decode().rstrip('='),'10'] for name in removed]
    rows.append([record_path.removeprefix(core.SITE),'',''])
    output=io.StringIO();csv.writer(output).writerows(rows);put(app,record_path,output.getvalue().encode())
    policy={'schema':'litrev.windows.optional-pywin32-policy.v1','scope':'Public synthetic fixtures only',
        'wheel':dict(core.WHEEL),'omitted_directories':list(core.ALLOWED_DIRECTORIES),
        'omitted_files':omitted,'protected_files':protected,'record_path':record_path,
        'record_removed_entrypoints':removed,'wheel_record_files':record_files,
        'unsupported_optional_apis':['Optional Pythonwin/MAPI/ActiveScript APIs unavailable.']}
    policy_path=put(tmp_path,'policy.json',core.json_bytes(policy))
    report={'install':[{'metadata':{'name':'pywin32','version':'312'},'download_info':{
        'url':'https://files.pythonhosted.org/packages/public/'+core.WHEEL['filename'],
        'archive_info':{'hashes':{'sha256':core.WHEEL['sha256']}}}}]}
    report_path=put(tmp_path,'wheel-report.json',json.dumps(report).encode())
    return app,resources,policy_path,policy,report_path,report


def test_prune_is_exact_bound_and_retains_every_other_python_byte(tmp_path):
    app,resources,policy_path,policy,report_path,_=inputs(tmp_path)
    before=snapshot(app);binding=core.prune_optional_pywin32(resources,report_path,policy_path=policy_path)
    after=snapshot(app)
    assert set(after)==(set(before)-set(policy['omitted_files']))|{core.POLICY_COPY_PATH,core.RECEIPT_PATH}
    for name,value in before.items():
        if name not in policy['omitted_files']:assert after[name]==value
    assert all(not (app/name).exists() for name in core.ALLOWED_DIRECTORIES)
    assert (app/core.POLICY_COPY_PATH).read_bytes()==policy_path.read_bytes()
    receipt=json.loads((app/core.RECEIPT_PATH).read_text())
    assert receipt['omitted_files']==policy['omitted_files'] and receipt['protected_files']==policy['protected_files']
    assert receipt['policy_sha256']==hashlib.sha256(policy_path.read_bytes()).hexdigest()
    assert receipt['unsupported_optional_apis']==policy['unsupported_optional_apis']
    assert binding['receipt_sha256']==hashlib.sha256((app/core.RECEIPT_PATH).read_bytes()).hexdigest()
    assert binding['omitted_file_count']==3 and binding['runtime_execution']==receipt['runtime_execution']=='NOT_RUN'
    retained={name:entry(value[1]) for name,value in after.items() if name.startswith('resources/python/')}
    assert receipt['preserved_python_inventory']=={'files':len(retained),'bytes':sum(row['bytes'] for row in retained.values()),'sha256':hashlib.sha256(core.json_bytes(retained)).hexdigest()}


@pytest.mark.parametrize('mutation',[
    'changed_optional','extra_optional','empty_extra_directory','linked_optional','linked_directory',
    'changed_protected','changed_record','wrong_wheel','wrong_wheel_hash','duplicate_wheel',
    'unknown_component','hidden_limitations','existing_receipt','existing_policy','omission_escape','overlap',
])
def test_prune_rejects_bad_input_before_any_deletion_or_output_write(tmp_path,mutation):
    app,resources,policy_path,policy,report_path,report=inputs(tmp_path)
    optional=app/next(iter(policy['omitted_files']))
    if mutation=='changed_optional':optional.write_bytes(b'changed')
    elif mutation=='extra_optional':put(app,core.ALLOWED_DIRECTORIES[0]+'/unknown.pyd',b'Unknown')
    elif mutation=='empty_extra_directory':(app/core.ALLOWED_DIRECTORIES[0]/'unexpected').mkdir()
    elif mutation=='linked_optional':optional.unlink();optional.symlink_to(tmp_path/'foreign')
    elif mutation=='linked_directory':
        directory=app/core.ALLOWED_DIRECTORIES[0];optional.unlink();directory.rmdir();directory.symlink_to(tmp_path,target_is_directory=True)
    elif mutation=='changed_protected':(app/next(iter(policy['protected_files']))).write_bytes(b'changed')
    elif mutation=='changed_record':(app/policy['record_path']).write_text('foreign.dll,sha256=AAAA,3\n')
    elif mutation=='wrong_wheel':report['install'][0]['metadata']['version']='313'
    elif mutation=='wrong_wheel_hash':report['install'][0]['download_info']['archive_info']['hashes']['sha256']='0'*64
    elif mutation=='duplicate_wheel':report['install']*=2
    elif mutation=='unknown_component':policy['omitted_directories'][0]=core.SITE+'win32'
    elif mutation=='hidden_limitations':policy['unsupported_optional_apis']=[]
    elif mutation=='existing_receipt':put(app,core.RECEIPT_PATH,b'Historical receipt')
    elif mutation=='existing_policy':put(app,core.POLICY_COPY_PATH,b'Historical policy')
    elif mutation=='omission_escape':policy['omitted_files']['resources/python/python.exe']=policy['protected_files']['resources/python/python.exe']
    elif mutation=='overlap':policy['protected_files'][next(iter(policy['omitted_files']))]=next(iter(policy['omitted_files'].values()))
    policy_path.write_bytes(core.json_bytes(policy));report_path.write_text(json.dumps(report))
    before=snapshot(app)
    with pytest.raises(ValueError):core.prune_optional_pywin32(resources,report_path,policy_path=policy_path)
    assert snapshot(app)==before


def test_existing_receipt_is_never_rewritten_on_repeated_prune(tmp_path):
    app,resources,policy_path,_,report_path,_=inputs(tmp_path)
    core.prune_optional_pywin32(resources,report_path,policy_path=policy_path)
    before=snapshot(app)
    with pytest.raises(ValueError,match='Never overwrite'):
        core.prune_optional_pywin32(resources,report_path,policy_path=policy_path)
    assert snapshot(app)==before
