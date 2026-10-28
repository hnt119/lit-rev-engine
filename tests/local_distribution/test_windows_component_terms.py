"""Active packaging gates, not Windows UI execution or legal certification."""
import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path('apps/desktop/notices/windows-distribution')
DISPLAY='MICROSOFT_COMPONENT_TERMS_WITH_LICENSES.txt'
OUTPUTS=('MICROSOFT_COMPONENT_TERMS.txt','MICROSOFT_COMPONENT_TERMS_INPUTS.json',
    'MICROSOFT_COMPONENT_LICENSE_ROUTE.json',DISPLAY)


def block(text,name,kind='Function',end='FunctionEnd'):
    found=re.search(r'^[ \t]*'+re.escape(kind)+' '+re.escape(name)+r'[ \t]*\n(.*?)^[ \t]*'+end+r'[ \t]*$',text,re.M|re.S)
    assert found,'Missing installer gate '+name
    return [line.strip() for line in found.group(1).splitlines() if line.strip() and not line.lstrip().startswith(';')]


def inputs(tmp_path):
    root=tmp_path/'source';(root/SOURCE).parent.mkdir(parents=True)
    shutil.copytree(ROOT/SOURCE,root/SOURCE)
    tree=ast.parse((ROOT/'scripts/build_desktop_installers.py').read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='copy_microsoft_component_terms')
    namespace={'ROOT':root,'json':json,'digest':lambda raw:sha256(raw).hexdigest()}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'<host-only-terms-copy>','exec'),namespace)
    payload=tmp_path/'payload';resources=payload/'resources'
    sdk=resources/'WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270';sdk.mkdir(parents=True)
    for name in ('LICENSE.rtf','LICENSE.rendered.txt'):
        shutil.copy2(ROOT/'apps/desktop/notices/windows-runtime/microsoft-sdk-10.0.28000.2270'/name,sdk/name)
    (resources/'python').mkdir()
    shutil.copy2(ROOT/'apps/desktop/notices/windows-runtime/python-3.12.15/LICENSE.txt',resources/'python/LICENSE.txt')
    return root,payload,resources,namespace['copy_microsoft_component_terms']


def test_active_nsis_uses_checked_state_only_and_rejects_silent_before_installation_writes():
    source=(ROOT/'apps/desktop/installer.nsi').read_text()
    nsh=(ROOT/'apps/desktop/windows-license-page.nsh').read_text()
    assert 'docs/windows-license-proposal' not in source+nsh
    pages=[source.index(name) for name in ('!insertmacro MUI_PAGE_WELCOME','!insertmacro LitRevMicrosoftTermsPage','!insertmacro MUI_PAGE_INSTFILES')]
    assert pages==sorted(pages)
    assert 'LitRevMicrosoftTermsPage "${PAYLOAD}\\resources\\'+DISPLAY+'"' in source
    assert '!define MUI_LICENSEPAGE_CHECKBOX' in nsh
    show=block(nsh,'LitRevMicrosoftTermsShow');leave=block(nsh,'LitRevMicrosoftTermsLeave')
    assert show[0]=='StrCpy $LitRevMicrosoftTermsAccepted "0"'
    assert 'SendMessage $0 ${BM_SETCHECK} ${BST_UNCHECKED} 0' in show and 'EnableWindow $0 0' in show
    assert not any('${BST_CHECKED}' in line for line in show)
    assert 'SendMessage $0 ${BM_GETCHECK} 0 0 $1' in leave
    assert leave.index('StrCmp $1 ${BST_CHECKED} litrev_ms_terms_accepted') < leave.index('StrCpy $LitRevMicrosoftTermsAccepted "1"')
    assert 'StrCpy $LitRevMicrosoftTermsAccepted "0"' in leave and 'Abort' in leave
    assert block(nsh,'LitRevRequireInteractiveMicrosoftTerms','!macro','!macroend')==[
        'StrCpy $LitRevMicrosoftTermsAccepted "0"','IfSilent 0 +3','SetErrorLevel 2','Abort']
    assert block(source,'.onInit')[0]=='!insertmacro LitRevRequireInteractiveMicrosoftTerms'
    assert block(source,'"Application"','Section','SectionEnd')[0]=='!insertmacro LitRevRequireAcceptedMicrosoftTerms'
    accepted=block(nsh,'LitRevRequireAcceptedMicrosoftTerms','!macro','!macroend')
    assert accepted[0]=='StrCmp $LitRevMicrosoftTermsAccepted "1" +4' and accepted[-2:]==['SetErrorLevel 2','Abort']
    assert not any(x in source+nsh for x in ('$CMDLINE','GetOptions','GetParameters','/ACCEPT','SetSilent normal'))


def test_pinned_full_text_route_and_input_copies_share_the_actual_display_receipt(tmp_path):
    root,payload,resources,copy=inputs(tmp_path)
    original={p.relative_to(resources).as_posix():p.read_bytes() for p in resources.rglob('*') if p.is_file()}
    result=copy(resources);manifest=json.loads((root/SOURCE/'MANIFEST.json').read_text())
    combined=(resources/DISPLAY).read_bytes();source=root/SOURCE
    assert combined.startswith(b'\xef\xbb\xbf')
    full=[source/'MICROSOFT_COMPONENT_TERMS.txt',resources/'WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270/LICENSE.rendered.txt',resources/'python/LICENSE.txt']
    assert all(p.read_bytes() in combined for p in full)
    assert (resources/'MICROSOFT_COMPONENT_TERMS.txt').read_bytes()==full[0].read_bytes()
    assert (resources/'MICROSOFT_COMPONENT_TERMS_INPUTS.json').read_bytes()==(source/'MANIFEST.json').read_bytes()
    assert (resources/'MICROSOFT_COMPONENT_LICENSE_ROUTE.json').read_bytes()==(source/'LICENSE_ROUTE.json').read_bytes()
    assert result['schema']=='litrev.windows.microsoft-component-terms.v1'
    assert result['displayed_and_retained_path']=='resources/'+DISPLAY
    assert result['displayed_and_retained_bytes']==len(combined) and result['displayed_and_retained_sha256']==sha256(combined).hexdigest()
    for name,p in [('terms',resources/'MICROSOFT_COMPONENT_TERMS.txt'),('input_manifest',resources/'MICROSOFT_COMPONENT_TERMS_INPUTS.json'),('route_record',resources/'MICROSOFT_COMPONENT_LICENSE_ROUTE.json')]:
        assert result[name+'_path']==p.relative_to(payload).as_posix() and result[name+'_sha256']==sha256(p.read_bytes()).hexdigest()
    assert result['inputs']==manifest['inputs'] and result['windows_interaction']=='NOT_RUN'
    assert result['silent_installation']=='rejected; no unattended acceptance flag'
    assert all((resources/name).read_bytes()==raw for name,raw in original.items())
    assert not (resources/'WINDOWS_DEPENDENCY_NOTICES'/DISPLAY).exists()
    assert set(result['inputs'])=={'component_terms','complete_sdk_license_readable','complete_sdk_license_authoritative','complete_python_license'}


@pytest.mark.parametrize('mutation',['raw_terms','sdk_readable','sdk_rtf','python','route','manifest_role','manifest_schema'])
def test_changed_or_incomplete_inputs_are_rejected_before_any_new_output(tmp_path,mutation):
    root,_,resources,copy=inputs(tmp_path)
    files={'raw_terms':root/SOURCE/'MICROSOFT_COMPONENT_TERMS.txt',
        'sdk_readable':resources/'WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270/LICENSE.rendered.txt',
        'sdk_rtf':resources/'WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270/LICENSE.rtf',
        'python':resources/'python/LICENSE.txt','route':root/SOURCE/'LICENSE_ROUTE.json'}
    if mutation in files:files[mutation].write_bytes(b'Unknown replacement')
    else:
        path=root/SOURCE/'MANIFEST.json';manifest=json.loads(path.read_text())
        if mutation=='manifest_role':manifest['inputs']['unexpected']={'bytes':0,'sha256':'0'*64}
        else:manifest['schema']='unknown'
        path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):copy(resources)
    assert all(not (resources/name).exists() for name in OUTPUTS)


@pytest.mark.parametrize('name',OUTPUTS)
@pytest.mark.parametrize('kind',['existing','dangling_link'])
def test_output_collisions_are_rejected_before_any_new_output(tmp_path,name,kind):
    _,_,resources,copy=inputs(tmp_path);target=resources/name;foreign=tmp_path/'foreign.txt'
    if kind=='existing':target.write_bytes(b'Historical file')
    else:target.symlink_to(foreign)
    with pytest.raises(ValueError,match='Do not overwrite'):copy(resources)
    assert all(not (resources/n).exists() for n in OUTPUTS if n!=name)
    assert not foreign.exists()
    if kind=='existing':assert target.read_bytes()==b'Historical file'
    else:assert target.is_symlink()


def test_terms_metadata_and_retained_files_are_bound_before_installed_manifest():
    tree=ast.parse((ROOT/'scripts/build_desktop_installers.py').read_text())
    assembly=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='assemble_windows')
    calls={n.func.id:n.lineno for n in ast.walk(assembly) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    writes={}
    for n in ast.walk(assembly):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='write_bytes':
            path=n.func.value
            if isinstance(path,ast.BinOp) and isinstance(path.right,ast.Constant):writes[path.right.value]=n.lineno
    assert calls['copy_windows_dependency_notices'] < calls['copy_microsoft_component_terms'] < writes['DESKTOP_RELEASE.json'] < writes['INSTALLATION.json']


def test_host_nsis_compiles_the_active_page_only_in_an_inert_public_fixture(tmp_path):
    compiler=os.environ.get('LITREV_TEST_MAKENSIS');sdk=os.environ.get('LITREV_TEST_NSISDIR')
    if not compiler or not sdk:pytest.skip('Opt-in host compiler unavailable; no install/download/Windows execution')
    header=Path(compiler).read_bytes()[:8]
    assert header[:4]==b'\xcf\xfa\xed\xfe' and struct.unpack_from('<I',header,4)[0]==0x100000c
    env={**os.environ,'NSISDIR':sdk}
    version=subprocess.run([compiler,'-VERSION'],env=env,capture_output=True,text=True)
    assert version.returncode==0 and version.stdout.strip()=='v3.13'
    _,payload,resources,copy=inputs(tmp_path);copy(resources)
    for name in ('LiteratureReviewEngine.exe','resources/python/python.exe','resources/engine/scripts/desktop_install_root.py'):
        path=payload/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'Public inert fixture only; never execute as an application.\n')
    (payload/'INSTALLATION.json').write_text(json.dumps({'fixture':'INERT; not a release artifact'}))
    output=tmp_path/'INERT-active-terms-fixture.exe'
    args=[compiler,'-V4','-NOCD','-DPRODUCT_VERSION=0.0.0-inert-terms',
        '-DPAYLOAD_MANIFEST_SHA='+'a'*64,'-DPAYLOAD='+str(payload),'-DOUTPUT_FILE='+str(output),str(ROOT/'apps/desktop/installer.nsi')]
    pre=subprocess.run([*args[:3],'-PPO',*args[3:]],env=env,capture_output=True,text=True,timeout=60)
    assert pre.returncode==0,pre.stderr
    assert 'LicenseForceSelection checkbox' in pre.stdout and DISPLAY in pre.stdout
    assert block(pre.stdout,'.onInit')[:4]==['StrCpy $LitRevMicrosoftTermsAccepted "0"','IfSilent 0 +3','SetErrorLevel 2','Abort']
    compiled=subprocess.run(args,env=env,capture_output=True,text=True,timeout=60)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    assert output.read_bytes()[:2]==b'MZ' and 'warning ' not in (compiled.stdout+compiled.stderr).lower()
