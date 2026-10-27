"""macOS-capable static fixtures only: no Windows binary, VM or app execution."""
import hashlib
import base64
import csv
import io
import json
from pathlib import Path
import struct
import pytest
from scripts import audit_windows_payload as audit


def pe(machine=0x8664, regular=None, delayed=None):
    data=bytearray(1536);data[:2]=b'MZ';struct.pack_into('<I',data,60,128)
    data[128:132]=b'PE\0\0';struct.pack_into('<HH',data,132,machine,1)
    struct.pack_into('<H',data,148,240);optional=152
    struct.pack_into('<H',data,optional,0x20b)
    struct.pack_into('<Q',data,optional+24,0x140000000)
    struct.pack_into('<I',data,optional+60,512)
    struct.pack_into('<I',data,optional+108,16)
    section=optional+240;data[section:section+6]=b'.rdata'
    struct.pack_into('<IIII',data,section+8,1024,4096,1024,512)
    if regular:
        struct.pack_into('<II',data,optional+112+8,4096,40)
        struct.pack_into('<IIIII',data,512,0,0,0,4352,0)
        name=regular.encode()+b'\0';data[768:768+len(name)]=name
    if delayed:
        struct.pack_into('<II',data,optional+112+13*8,4160,64)
        struct.pack_into('<IIIIIIII',data,576,1,4416,0,0,0,0,0,0)
        name=delayed.encode()+b'\0';data[832:832+len(name)]=name
    return bytes(data)


def put(root,relative,raw):
    p=root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);return p


def dist(site,name='fixture',version='1.0',requires=(),tag='py3-none-any',python=None):
    root=site/(name.replace('-','_')+'-'+version+'.dist-info');root.mkdir(parents=True)
    body=f'Name: {name}\nVersion: {version}\n'
    if python:body+=f'Requires-Python: {python}\n'
    body+=''.join('Requires-Dist: '+r+'\n' for r in requires)
    (root/'METADATA').write_text(body);(root/'WHEEL').write_text('Wheel-Version: 1.0\nTag: '+tag+'\n')


def bind_manifest(payload,source='a'*40):
    files={p.relative_to(payload).as_posix():{'bytes':p.stat().st_size,'sha256':audit.sha(p)} for p in payload.rglob('*') if p.is_file() and p.name!='INSTALLATION.json'}
    value={'schema':'litrev.desktop.installed-files.v1','source_commit':source,'app_id':'org.hnt119.litrev.desktop','version':'0.3.0-test.1','files':files}
    (payload/'INSTALLATION.json').write_text(json.dumps(value));return value


def subset_fixture(root,payload):
    """Synthetic bytes under the exact reviewed boundaries; no target loading."""
    omitted={};protected={}
    dist(payload/'resources/python/Lib/site-packages','pywin32','312',tag='cp312-cp312-win_amd64')
    for name in audit.OPTIONAL_DIRECTORIES:
        p=put(payload,name+'/optional.txt',b'Public optional fixture\n')
        omitted[p.relative_to(payload).as_posix()]={'bytes':p.stat().st_size,'sha256':audit.sha(p)}
    for name in audit.CORE_FILES:
        if not name.startswith('resources/python/'):continue
        p=payload/name
        if not p.exists():p=put(payload,name,pe() if name.endswith(('.exe','.dll','.pyd')) else b'# Public synthetic loader\n')
        protected[name]={'bytes':p.stat().st_size,'sha256':audit.sha(p)}
    for p in (payload/'resources/python/Lib/site-packages/pywin32-312.dist-info').iterdir():
        protected[p.relative_to(payload).as_posix()]={'bytes':p.stat().st_size,'sha256':audit.sha(p)}
    policy={'schema':'litrev.windows.optional-pywin32-policy.v1',
        'wheel':{'name':'pywin32','version':'312','filename':'pywin32-312-cp312-cp312-win_amd64.whl','sha256':'b457f6d628a47e8a7346ce22acb7e1a46a4a78b52e1d17e1af56871bd19a93bc'},
        'omitted_directories':list(audit.OPTIONAL_DIRECTORIES),'omitted_files':omitted,
        'protected_files':protected,'unsupported_optional_apis':['Pythonwin GUI/DDE','MAPI/Exchange','ActiveScript debugger'],
        'scope':'Synthetic static fixture only', 'record_path':audit.PYWIN32_RECORD,
        'record_removed_entrypoints':list(audit.REMOVED_PYWIN32_ENTRYPOINTS)}
    record_files={name:row for name,row in {**protected,**omitted}.items() if name.startswith('resources/python/Lib/site-packages/')}
    policy['wheel_record_files']=record_files
    rows=[]
    for name,row in record_files.items():
        encoded=base64.urlsafe_b64encode(bytes.fromhex(row['sha256'])).decode().rstrip('=')
        rows.append([name.removeprefix('resources/python/Lib/site-packages/'),'sha256='+encoded,str(row['bytes'])])
    rows += [[name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(b'Already omitted entrypoint').digest()).decode().rstrip('='),'25'] for name in audit.REMOVED_PYWIN32_ENTRYPOINTS]
    rows.append([audit.PYWIN32_RECORD.removeprefix('resources/python/Lib/site-packages/'),'',''])
    output=io.StringIO();csv.writer(output).writerows(rows)
    put(payload,audit.PYWIN32_RECORD,output.getvalue().encode())
    p=put(root,audit.SUBSET_POLICY.as_posix(),(json.dumps(policy,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode())
    return p,policy


def bind_subset_receipt(payload,policy_file,policy):
    import shutil
    for name in audit.OPTIONAL_DIRECTORIES:shutil.rmtree(payload/name)
    put(payload,audit.PACKAGED_SUBSET_POLICY,policy_file.read_bytes())
    retained=audit.inventory(payload/'resources/python',payload)
    receipt={'schema':'litrev.windows.optional-pywin32-subset.v1','policy_path':audit.SUBSET_POLICY.as_posix(),
        'policy_sha256':audit.sha(policy_file),'packaged_policy_path':audit.PACKAGED_SUBSET_POLICY,
        'wheel':policy['wheel'],
        'omitted_directories':policy['omitted_directories'],'omitted_files':policy['omitted_files'],
        'protected_files':policy['protected_files'],'unsupported_optional_apis':policy['unsupported_optional_apis'],
        'preserved_python_inventory':{'files':len(retained),'bytes':sum(row['bytes'] for row in retained.values()),'sha256':audit.inventory_digest(retained)},
        'runtime_execution':'NOT_RUN'}
    p=put(payload,audit.SUBSET_RECEIPT,json.dumps(receipt).encode())
    metadata={'windows_optional_pywin32_subset':{'schema':'litrev.windows.optional-pywin32-subset-binding.v1',
        'receipt_path':audit.SUBSET_RECEIPT,'receipt_sha256':audit.sha(p),'omitted_file_count':len(policy['omitted_files']),'runtime_execution':'NOT_RUN'}}
    return p,receipt,metadata


def test_pe_regular_and_delay_imports_are_read_without_execution():
    result=audit.pe_info(pe(regular='KERNEL32.dll',delayed='thirdparty.dll'))
    assert result['machine']==0x8664 and result['optional_magic']==0x20b
    assert result['imports']==[{'dll':'kernel32.dll','delay':False},{'dll':'thirdparty.dll','delay':True}]


@pytest.mark.parametrize('mutation',['offset','section','rva','name'])
def test_malformed_pe_cannot_produce_a_false_import_pass(mutation):
    raw=bytearray(pe(regular='thirdparty.dll'))
    if mutation=='offset':struct.pack_into('<I',raw,60,0xfffffff0)
    elif mutation=='section':struct.pack_into('<I',raw,152+240+20,0xfffffff0)
    elif mutation=='rva':struct.pack_into('<I',raw,512+12,0x90000000)
    else:raw[768:782]=b'../unsafe.dll\0'
    with pytest.raises(ValueError):audit.pe_info(bytes(raw))


def test_dll_closure_keeps_explicit_os_exceptions_and_fails_missing_bundled_import(tmp_path):
    p=put(tmp_path,'LiteratureReviewEngine.exe',pe(regular='KERNEL32.dll',delayed='private.dll'))
    files={'LiteratureReviewEngine.exe':{'sha256':audit.sha(p)}}
    result=audit.native_closure(tmp_path,files)
    assert result['unresolved']==[{'path':'LiteratureReviewEngine.exe','dll':'private.dll','delay':True}]
    assert result['system_exceptions'][0]['dll']=='kernel32.dll'
    q=put(tmp_path,'private.dll',pe());files['private.dll']={'sha256':audit.sha(q)}
    assert not audit.native_closure(tmp_path,files)['unresolved']


def test_arm_and_x86_are_not_generic_runtime_exceptions(tmp_path):
    p=put(tmp_path,'foreign.exe',pe(machine=0xaa64))
    with pytest.raises(ValueError,match='architecture'):audit.native_closure(tmp_path,{'foreign.exe':{'sha256':audit.sha(p)}})
    name='resources/python/Lib/site-packages/pip/_vendor/distlib/t64-arm.exe'
    p=put(tmp_path,name,pe(machine=0xaa64))
    result=audit.native_closure(tmp_path,{name:{'sha256':audit.sha(p)}})
    assert result['files'][0]['auxiliary_not_core'] is True
    p.write_bytes(pe(machine=0x14c))
    with pytest.raises(ValueError,match='architecture'):audit.native_closure(tmp_path,{name:{'sha256':audit.sha(p)}})


def test_target_metadata_uses_all_windows_markers_and_does_not_enable_optional_extras(tmp_path,monkeypatch):
    monkeypatch.setattr(audit,'ROOT',tmp_path)
    (tmp_path/'requirements-hosted.txt').write_text('fixture==1.0\n')
    site=tmp_path/'site'
    edge='dependency>=2; os_name == "nt" and sys_platform == "win32" and platform_system == "Windows" and platform_machine == "AMD64" and python_version == "3.12" and python_full_version == "3.12.15" and implementation_name == "cpython"'
    dist(site,requires=[edge,'optional; extra == "neural"'])
    result=audit.dependency_closure(site)
    assert any('dependency' in x for x in result['failures'])
    assert not any('optional' in x for x in result['failures'])
    dist(site,'dependency','2.0',tag='cp312-cp312-win_amd64')
    assert audit.dependency_closure(site)['failures']==[]
    (tmp_path/'requirements-hosted.txt').write_text('fixture[neural]==1.0\n')
    assert any('optional' in x for x in audit.dependency_closure(site)['failures'])


def test_macos_wheel_or_unsupported_python_is_not_a_windows_runtime(tmp_path,monkeypatch):
    monkeypatch.setattr(audit,'ROOT',tmp_path);(tmp_path/'requirements-hosted.txt').write_text('fixture==1.0\n')
    dist(tmp_path/'site',tag='cp312-cp312-macosx_11_0_arm64',python='>=3.13')
    failed=audit.dependency_closure(tmp_path/'site')['failures']
    assert any('wheel tag' in x for x in failed) and any('Requires-Python' in x for x in failed)


def test_manifest_rejects_extra_mutated_and_symlinked_files(tmp_path):
    put(tmp_path,'ordinary.txt',b'Public synthetic data');bind_manifest(tmp_path)
    audit.check_manifest(tmp_path,'a'*40)
    extra=put(tmp_path,'extra.txt',b'Unbound');
    with pytest.raises(ValueError,match='extra'):audit.check_manifest(tmp_path,'a'*40)
    extra.unlink();(tmp_path/'ordinary.txt').write_bytes(b'Changed')
    with pytest.raises(ValueError,match='digest'):audit.check_manifest(tmp_path,'a'*40)
    (tmp_path/'ordinary.txt').unlink();(tmp_path/'ordinary.txt').symlink_to('/not/read')
    with pytest.raises(ValueError,match='symlink'):audit.check_manifest(tmp_path,'a'*40)


def test_host_extracted_payload_must_match_each_bound_byte(tmp_path):
    payload=tmp_path/'payload';payload.mkdir();put(payload,'record.txt',b'Public fixture');bind_manifest(payload)
    extracted=tmp_path/'extracted';copy=extracted/'app';copy.mkdir(parents=True)
    for name in ['record.txt','INSTALLATION.json']:(copy/name).write_bytes((payload/name).read_bytes())
    assert audit.extracted_matches(extracted,payload)['status']=='PASS'
    (copy/'record.txt').write_text('Changed during extraction')
    with pytest.raises(ValueError,match='digest|mismatch'):audit.extracted_matches(extracted,payload)
    (copy/'record.txt').write_bytes((payload/'record.txt').read_bytes())
    (copy/'unbound.txt').write_text('Unexpected extracted runtime')
    with pytest.raises(ValueError,match='extra'):audit.extracted_matches(extracted,payload)


def test_complete_static_fixture_preserves_literal_not_run_and_owner_reason(tmp_path,monkeypatch):
    source='a'*40;monkeypatch.setattr(audit,'ROOT',tmp_path)
    (tmp_path/'requirements-hosted.txt').write_text('fixture==1.0\n')
    payload=tmp_path/'payload';payload.mkdir()
    for name in ('LiteratureReviewEngine.exe',*audit.CORE_FILES):
        put(payload,name,pe() if name.endswith(('.exe','.dll','.pyd')) else b'# Public synthetic source\n')
    put(payload,'resources/engine/src/__init__.py',b'# Synthetic application\n')
    site=payload/'resources/python/Lib/site-packages';dist(site)
    for package in ('fastapi','uvicorn','pydantic','pydantic_core','starlette','anyio'):put(site,package+'/__init__.py',b'# Synthetic package\n')
    put(site,'pydantic_core/_pydantic_core.cp312-win_amd64.pyd',pe())
    put(site,'win32/lib/pywin32_bootstrap.py',b'# os.add_dll_directory for pywin32_system32; synthetic only\n')
    put(site,'pywin32.pth',b'win32\nwin32\\lib\npythonwin\nimport pywin32_bootstrap\n')
    subset_fixture(tmp_path,payload)
    put(payload,'resources/DESKTOP_RELEASE.json',json.dumps({'source_commit':source,'target':'win32-x64','version':'0.3.0-test.1','core_runtimes_bundled':True,'web_build_binding':{'source_commit':source}}).encode())
    put(payload,'resources/app/product.json',json.dumps({'version':'0.3.0-test.1','data_name':'LiteratureReviewEngineDesktop'}).encode())
    bind_manifest(payload,source)
    report=audit.audit(payload,source)
    assert report['status']=='PASS'
    for field in ('runtime_execution','vm_execution','gui_execution','installed_execution'):assert report[field]=='NOT_RUN'
    assert 'Owner explicitly skipped' in report['owner_skip_reason']
    assert report['application_imports']['status']=='PASS'
    assert report['optional_pywin32_subset']['status']=='NOT_APPLIED'


def test_security_bootstrap_and_loader_files_are_explicit_core_prerequisites():
    for name in ('pythoncom.py','win32/_win32sysloader.pyd','win32/lib/pywintypes.py',
                 'pywin32.pth','win32/lib/pywin32_bootstrap.py',
                 'pywin32_system32/pywintypes312.dll','pywin32_system32/pythoncom312.dll'):
        assert 'resources/python/Lib/site-packages/'+name in audit.CORE_FILES
    for name in ('vcruntime140.dll','vcruntime140_1.dll'):
        assert 'resources/python/'+name in audit.CORE_FILES


@pytest.mark.parametrize('source',[
    'import win32ui\n', 'from pywin import mfc\n',
    'from win32com import mapi\n', 'from win32com.axdebug import axdebug\n',
    'import importlib; importlib.import_module("win32comext.mapi")\n',
    'from importlib import import_module as load; load("win32com.mapi")\n',
    '__import__("dde")\n',
])
def test_application_must_not_acquire_dependency_on_excluded_optional_apis(tmp_path,source):
    (tmp_path/'scripts').mkdir();put(tmp_path,'src/new_feature.py',source.encode())
    with pytest.raises(ValueError,match='imports omitted optional API'):
        audit.source_import_guard(tmp_path)


def test_application_guard_retains_required_security_imports_and_rejects_unparseable_source(tmp_path):
    (tmp_path/'scripts').mkdir()
    p=put(tmp_path,'src/security.py',b'import pywintypes, win32api, win32file, win32security, win32job\n')
    assert audit.source_import_guard(tmp_path)['files_scanned']==1
    p.write_text('invalid syntax !')
    with pytest.raises(ValueError,match='Cannot inspect application imports'):
        audit.source_import_guard(tmp_path)


def test_mfc_and_msvcp_are_never_converted_to_windows_os_exceptions(tmp_path):
    assert not {'mfc140u.dll','msvcp140.dll'} & audit.SYSTEM_DLLS
    for name in ('mfc140u.dll','msvcp140.dll'):
        p=put(tmp_path,'core.pyd',pe(regular=name))
        assert audit.native_closure(tmp_path,{'core.pyd':{'sha256':audit.sha(p)}})['unresolved'][0]['dll']==name


def test_subset_accepts_only_bound_omissions_and_preserves_old_complete_inventory(tmp_path,monkeypatch):
    monkeypatch.setattr(audit,'ROOT',tmp_path)
    payload=tmp_path/'payload';payload.mkdir()
    policy_file,policy=subset_fixture(tmp_path,payload)
    assert audit.verify_pywin32_subset(payload,{})['status']=='NOT_APPLIED'
    receipt_file,receipt,metadata=bind_subset_receipt(payload,policy_file,policy)
    result=audit.verify_pywin32_subset(payload,metadata)
    assert result['status']=='PASS' and result['omitted_files']==3
    assert result['preserved_python_inventory']==receipt['preserved_python_inventory']
    assert result['receipt_sha256']==audit.sha(receipt_file)


@pytest.mark.parametrize('mutation',[
    'receipt_hash','policy_hash','packaged_policy','omitted_keyset','protected_keyset',
    'hidden_limitations','unknown_field','reintroduced_component','retained_mutation','missing_loader',
])
def test_subset_rejects_receipt_tampering_or_unexpected_payload_changes(tmp_path,monkeypatch,mutation):
    monkeypatch.setattr(audit,'ROOT',tmp_path)
    payload=tmp_path/'payload';payload.mkdir()
    policy_file,policy=subset_fixture(tmp_path,payload)
    receipt_file,receipt,metadata=bind_subset_receipt(payload,policy_file,policy)
    if mutation=='receipt_hash':metadata['windows_optional_pywin32_subset']['receipt_sha256']='0'*64
    elif mutation=='policy_hash':receipt['policy_sha256']='0'*64
    elif mutation=='packaged_policy':(payload/audit.PACKAGED_SUBSET_POLICY).write_text('{}')
    elif mutation=='omitted_keyset':receipt['omitted_files'].pop(next(iter(receipt['omitted_files'])))
    elif mutation=='protected_keyset':receipt['protected_files'].pop(next(iter(receipt['protected_files'])))
    elif mutation=='hidden_limitations':receipt['unsupported_optional_apis']=[]
    elif mutation=='unknown_field':receipt['unexpected_override']='ignore failures'
    elif mutation=='reintroduced_component':put(payload,audit.OPTIONAL_DIRECTORIES[0]+'/optional.txt',b'Reintroduced')
    elif mutation=='retained_mutation':put(payload,'resources/python/unreviewed.txt',b'Unexpected retained data')
    elif mutation=='missing_loader':(payload/'resources/python/Lib/site-packages/win32/_win32sysloader.pyd').unlink()
    if mutation in {'policy_hash','omitted_keyset','protected_keyset','hidden_limitations','unknown_field'}:
        receipt_file.write_text(json.dumps(receipt))
        metadata['windows_optional_pywin32_subset']['receipt_sha256']=audit.sha(receipt_file)
    with pytest.raises(ValueError):audit.verify_pywin32_subset(payload,metadata)


def test_absent_descriptor_cannot_hide_partial_or_empty_component_directories(tmp_path,monkeypatch):
    monkeypatch.setattr(audit,'ROOT',tmp_path)
    payload=tmp_path/'payload';payload.mkdir()
    _,policy=subset_fixture(tmp_path,payload)
    (payload/next(iter(policy['omitted_files']))).unlink()
    with pytest.raises(ValueError,match='Missing optional subset receipt'):
        audit.verify_pywin32_subset(payload,{})


def test_policy_must_protect_core_even_when_receipt_and_manifest_are_rebound(tmp_path,monkeypatch):
    monkeypatch.setattr(audit,'ROOT',tmp_path)
    payload=tmp_path/'payload';payload.mkdir()
    policy_file,policy=subset_fixture(tmp_path,payload)
    policy['protected_files'].pop('resources/python/Lib/site-packages/win32/_win32sysloader.pyd')
    policy_file.write_text(json.dumps(policy))
    _,_,metadata=bind_subset_receipt(payload,policy_file,policy)
    with pytest.raises(ValueError,match='does not protect every Core'):
        audit.verify_pywin32_subset(payload,metadata)


def test_retained_module_importing_omitted_binary_is_not_suppressed(tmp_path):
    p=put(tmp_path,'retained.pyd',pe(regular='win32ui.pyd'))
    result=audit.native_closure(tmp_path,{'retained.pyd':{'sha256':audit.sha(p)}})
    assert result['unresolved']==[{'path':'retained.pyd','dll':'win32ui.pyd','delay':False}]


def test_pyd_imports_are_dll_dependencies_and_java_magic_is_not_macho(tmp_path):
    p=put(tmp_path,'module.pyd',pe(regular='sibling.pyd'))
    q=put(tmp_path,'sibling.pyd',pe())
    java=put(tmp_path,'notice.class',b'\xca\xfe\xba\xbe\x00\x00\x00\x41Public fixture')
    files={x.relative_to(tmp_path).as_posix():{'sha256':audit.sha(x)} for x in (p,q,java)}
    assert audit.native_closure(tmp_path,files)['unresolved']==[]


def test_cli_rejects_report_inside_payload_or_extraction_before_any_write(tmp_path):
    import subprocess
    import sys
    script=Path(audit.__file__).resolve()
    payload=tmp_path/'payload';payload.mkdir()
    extracted=tmp_path/'extracted';extracted.mkdir()
    for destination in (payload/'audit.json',extracted/'audit.json'):
        result=subprocess.run([sys.executable,'-B',str(script),'--payload',str(payload),'--source-sha','a'*40,'--extracted',str(extracted),'--report',str(destination)],capture_output=True,text=True)
        assert result.returncode==2 and 'outside the audited payload' in result.stderr
        assert not destination.exists()
        assert list(payload.iterdir())==[] and list(extracted.iterdir())==[]
