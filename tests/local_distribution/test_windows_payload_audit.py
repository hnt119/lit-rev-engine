"""macOS-capable static fixtures only: no Windows binary, VM or app execution."""
import hashlib
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
    site=payload/'resources/python/Lib/site-packages';dist(site)
    for package in ('fastapi','uvicorn','pydantic','pydantic_core','starlette','anyio'):put(site,package+'/__init__.py',b'# Synthetic package\n')
    put(site,'pydantic_core/_pydantic_core.cp312-win_amd64.pyd',pe())
    put(site,'win32/lib/pywin32_bootstrap.py',b'# os.add_dll_directory for pywin32_system32; synthetic only\n')
    put(site,'pywin32.pth',b'win32\nwin32\\lib\npythonwin\nimport pywin32_bootstrap\n')
    put(payload,'resources/DESKTOP_RELEASE.json',json.dumps({'source_commit':source,'target':'win32-x64','version':'0.3.0-test.1','core_runtimes_bundled':True,'web_build_binding':{'source_commit':source}}).encode())
    put(payload,'resources/app/product.json',json.dumps({'version':'0.3.0-test.1','data_name':'LiteratureReviewEngineDesktop'}).encode())
    bind_manifest(payload,source)
    report=audit.audit(payload,source)
    assert report['status']=='PASS'
    for field in ('runtime_execution','vm_execution','gui_execution','installed_execution'):assert report[field]=='NOT_RUN'
    assert 'Owner explicitly skipped' in report['owner_skip_reason']


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
