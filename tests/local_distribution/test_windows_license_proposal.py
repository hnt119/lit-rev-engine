"""Inactive license proposal checks; no application or Windows execution.

The opt-in compiler check builds only an inert temporary NSIS fixture. It is
not an installer candidate, a GUI test, consent or redistribution permission.
"""
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
PROPOSAL=ROOT/'docs/windows-license-proposal'
TERMS='MICROSOFT_COMPONENT_TERMS_WITH_LICENSES.txt'


def body(text,name,kind='Function',end='FunctionEnd'):
    match=re.search(r'^[ \t]*'+re.escape(kind)+' '+re.escape(name)+r'[ \t]*\n(.*?)^[ \t]*'+end+r'[ \t]*$',text,re.M|re.S)
    assert match,'Missing proposal block: '+name
    return match.group(1)


def instructions(text):
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(';')]


def patched_tree(tmp_path):
    root=tmp_path/'fixture-source';(root/'apps/desktop').mkdir(parents=True);(root/'scripts').mkdir()
    shutil.copy2(ROOT/'apps/desktop/installer.nsi',root/'apps/desktop/installer.nsi')
    shutil.copy2(ROOT/'scripts/build_desktop_installers.py',root/'scripts/build_desktop_installers.py')
    shutil.copytree(PROPOSAL,root/'docs/windows-license-proposal')
    patch=root/'docs/windows-license-proposal/integration.patch'
    for args in (['--check'],[]):
        result=subprocess.run(['git','apply',*args,str(patch)],cwd=root,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
    return root


def prepare_terms(root,tmp_path):
    """Execute only the proposed pure host copy function, not the builder/app."""
    tree=ast.parse((root/'scripts/build_desktop_installers.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='copy_proposed_microsoft_component_terms')
    namespace={'ROOT':root,'digest':lambda data:sha256(data).hexdigest()}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<inactive-host-copy-proposal>','exec'),namespace)
    payload=tmp_path/'inert-payload';resources=payload/'resources'
    sdk=resources/'WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270';sdk.mkdir(parents=True)
    for name in ('LICENSE.rtf','LICENSE.rendered.txt'):
        shutil.copy2(ROOT/'apps/desktop/notices/windows-runtime/microsoft-sdk-10.0.28000.2270'/name,sdk/name)
    (resources/'python').mkdir()
    shutil.copy2(ROOT/'apps/desktop/notices/windows-runtime/python-3.12.15/LICENSE.txt',resources/'python/LICENSE.txt')
    return payload,namespace['copy_proposed_microsoft_component_terms']


def test_proposal_is_inactive_and_only_patches_the_two_declared_packaging_files():
    active=(ROOT/'apps/desktop/installer.nsi').read_text()
    builder=(ROOT/'scripts/build_desktop_installers.py').read_text()
    assert 'LitRevMicrosoftTerms' not in active and 'windows-license-proposal' not in active
    assert 'copy_proposed_microsoft_component_terms' not in builder
    patch=(PROPOSAL/'integration.patch').read_text()
    assert re.findall(r'^\+\+\+ b/(.+)$',patch,re.M)==['apps/desktop/installer.nsi','scripts/build_desktop_installers.py']
    text=(PROPOSAL/'MICROSOFT_COMPONENT_TERMS.txt').read_text()
    assert text.startswith('OWNER-REVIEW DRAFT') and 'INACTIVE' in text.splitlines()[0]
    assert 'not an independent grant of redistribution rights' in text
    assert 'The original Literature Review Engine code remains MIT.' in text


def test_unchecked_affirmative_choice_and_fail_closed_silent_and_section_guards(tmp_path):
    root=patched_tree(tmp_path);source=(root/'apps/desktop/installer.nsi').read_text()
    nsh=(PROPOSAL/'windows-license-page.nsh').read_text()
    pages=[source.index(name) for name in ('!insertmacro MUI_PAGE_WELCOME','!insertmacro LitRevMicrosoftTermsPage','!insertmacro MUI_PAGE_INSTFILES')]
    assert pages==sorted(pages)
    assert '!define MUI_LICENSEPAGE_CHECKBOX' in nsh
    show=body(nsh,'LitRevMicrosoftTermsShow');leave=body(nsh,'LitRevMicrosoftTermsLeave')
    assert 'StrCpy $LitRevMicrosoftTermsAccepted "0"' in show
    assert 'SendMessage $0 ${BM_SETCHECK} ${BST_UNCHECKED} 0' in show
    assert 'EnableWindow $0 0' in show and '${BST_CHECKED}' not in show
    assert 'SendMessage $0 ${BM_GETCHECK} 0 0 $1' in leave
    assert leave.index('StrCmp $1 ${BST_CHECKED}') < leave.index('StrCpy $LitRevMicrosoftTermsAccepted "1"')
    assert 'StrCpy $LitRevMicrosoftTermsAccepted "0"' in leave and 'Abort' in leave
    silent=body(nsh,'LitRevRequireInteractiveMicrosoftTerms',kind='!macro',end='!macroend')
    assert instructions(silent)==['StrCpy $LitRevMicrosoftTermsAccepted "0"','IfSilent 0 +3','SetErrorLevel 2','Abort']
    assert instructions(body(source,'.onInit'))[0]=='!insertmacro LitRevRequireInteractiveMicrosoftTerms'
    section=body(source,'"Application"',kind='Section',end='SectionEnd')
    assert instructions(section)[0]=='!insertmacro LitRevRequireAcceptedMicrosoftTerms'
    accepted=body(nsh,'LitRevRequireAcceptedMicrosoftTerms',kind='!macro',end='!macroend')
    assert instructions(accepted)[0]=='StrCmp $LitRevMicrosoftTermsAccepted "1" +4'
    assert 'SetErrorLevel 2' in accepted and 'Abort' in accepted
    assert not any(token in nsh+source for token in ('$CMDLINE','GetOptions','GetParameters','/ACCEPT','SetSilent normal'))


def test_full_text_is_displayed_and_retained_with_input_hashes_before_future_manifest(tmp_path):
    root=patched_tree(tmp_path);payload,copy=prepare_terms(root,tmp_path);resources=payload/'resources'
    before={p.relative_to(resources).as_posix():p.read_bytes() for p in resources.rglob('*') if p.is_file()}
    result=copy(resources);combined=(resources/TERMS).read_bytes()
    assert combined.startswith(b'\xef\xbb\xbf')
    draft=(PROPOSAL/'MICROSOFT_COMPONENT_TERMS.txt').read_bytes()
    sdk=resources/'WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270'
    assert draft in combined and (sdk/'LICENSE.rendered.txt').read_bytes() in combined
    assert (resources/'python/LICENSE.txt').read_bytes() in combined
    assert result['displayed_and_retained_path']=='resources/'+TERMS
    assert result['displayed_and_retained_sha256']==sha256(combined).hexdigest()
    assert result['windows_interaction']=='NOT_RUN' and result['status'].startswith('OWNER_REVIEW_REQUIRED')
    sources={'proposed_component_terms':PROPOSAL/'MICROSOFT_COMPONENT_TERMS.txt',
        'complete_sdk_license_readable':sdk/'LICENSE.rendered.txt','complete_sdk_license_authoritative':sdk/'LICENSE.rtf',
        'complete_python_license':resources/'python/LICENSE.txt'}
    assert result['inputs']=={name:{'bytes':p.stat().st_size,'sha256':sha256(p.read_bytes()).hexdigest()} for name,p in sources.items()}
    assert all((resources/name).read_bytes()==data for name,data in before.items())
    source=(root/'apps/desktop/installer.nsi').read_text()
    assert 'LitRevMicrosoftTermsPage "${PAYLOAD}\\resources\\'+TERMS+'"' in source
    tree=ast.parse((root/'scripts/build_desktop_installers.py').read_text())
    assembly=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='assemble_windows')
    calls={node.func.id:node.lineno for node in ast.walk(assembly) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)}
    manifests=[]
    for node in ast.walk(assembly):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='write_bytes':
            path=node.func.value
            if isinstance(path,ast.BinOp) and isinstance(path.right,ast.Constant) and path.right.value in ('DESKTOP_RELEASE.json','INSTALLATION.json'):manifests.append(node.lineno)
    assert len(manifests)==2
    assert calls['copy_windows_dependency_notices'] < calls['copy_proposed_microsoft_component_terms'] < min(manifests)
    assert not (resources/'WINDOWS_DEPENDENCY_NOTICES'/TERMS).exists()
    with pytest.raises(ValueError,match='Do not overwrite'):copy(resources)


@pytest.mark.parametrize('missing',['complete_sdk_license_readable','complete_sdk_license_authoritative','complete_python_license'])
def test_missing_full_vendor_text_prevents_even_proposal_packaging(tmp_path,missing):
    root=patched_tree(tmp_path);payload,copy=prepare_terms(root,tmp_path);resources=payload/'resources'
    files={'complete_sdk_license_readable':resources/'WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270/LICENSE.rendered.txt',
        'complete_sdk_license_authoritative':resources/'WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270/LICENSE.rtf',
        'complete_python_license':resources/'python/LICENSE.txt'}
    files[missing].unlink()
    with pytest.raises(ValueError,match='Require complete'):copy(resources)
    assert not (resources/TERMS).exists()


def test_dangling_display_destination_is_rejected_without_touching_foreign_path(tmp_path):
    root=patched_tree(tmp_path);payload,copy=prepare_terms(root,tmp_path);resources=payload/'resources'
    foreign=tmp_path/'foreign.txt';(resources/TERMS).symlink_to(foreign)
    with pytest.raises(ValueError,match='Do not overwrite'):copy(resources)
    assert not foreign.exists() and (resources/TERMS).is_symlink()


def test_proposal_readme_local_links_resolve_and_remain_review_only():
    path=PROPOSAL/'README.md';text=path.read_text()
    assert 'inactive' in text.lower() and 'NOT_RUN' in text
    checked=0
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)',text):
        if target.startswith(('https://','http://')):
            assert target.startswith('https://');continue
        local,_,fragment=target.partition('#')
        resolved=(path.parent/local).resolve() if local else path
        assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file(),target
        if fragment and resolved.suffix=='.md':
            headings=re.findall(r'^#{1,6}\s+(.+?)\s*#*$',resolved.read_text(),re.M)
            slugs={re.sub(r'[^\w\- ]','',heading.lower()).replace(' ','-') for heading in headings}
            assert fragment in slugs or ('id="'+fragment+'"') in resolved.read_text(),target
        checked+=1
    assert checked>=1


def test_pinned_host_nsis_preprocesses_and_compiles_only_an_inert_proposal_fixture(tmp_path):
    compiler=os.environ.get('LITREV_TEST_MAKENSIS');sdk=os.environ.get('LITREV_TEST_NSISDIR')
    if not compiler or not sdk:pytest.skip('Host NSIS compile not requested; no install/download/Windows execution')
    compiler=Path(compiler);header=compiler.read_bytes()[:8]
    assert header[:4]==b'\xcf\xfa\xed\xfe' and struct.unpack_from('<I',header,4)[0]==0x100000c,'This opt-in fixture uses the reviewed macOS arm64 compiler only'
    env={**os.environ,'NSISDIR':sdk}
    version=subprocess.run([str(compiler),'-VERSION'],env=env,capture_output=True,text=True)
    assert version.returncode==0 and version.stdout.strip()=='v3.13'
    root=patched_tree(tmp_path);payload,copy=prepare_terms(root,tmp_path);copy(payload/'resources')
    for name in ('LiteratureReviewEngine.exe','resources/python/python.exe','resources/engine/scripts/desktop_install_root.py'):
        path=payload/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'Public inert fixture; never execute as an application.\n')
    (payload/'INSTALLATION.json').write_text(json.dumps({'fixture':'INERT; not a research application or release artifact'}))
    output=tmp_path/'INERT-license-proposal-fixture.exe'
    args=[str(compiler),'-V4','-NOCD','-DPRODUCT_VERSION=0.0.0-proposal-fixture',
        '-DPAYLOAD_MANIFEST_SHA='+'a'*64,'-DPAYLOAD='+str(payload),'-DOUTPUT_FILE='+str(output),str(root/'apps/desktop/installer.nsi')]
    preprocess=subprocess.run([*args[:3],'-PPO',*args[3:]],cwd=root,env=env,capture_output=True,text=True,timeout=60)
    assert preprocess.returncode==0,preprocess.stderr
    assert 'LicenseForceSelection checkbox' in preprocess.stdout
    assert TERMS in preprocess.stdout and 'Function LitRevMicrosoftTermsLeave' in preprocess.stdout
    assert instructions(body(preprocess.stdout,'.onInit'))[:4]==['StrCpy $LitRevMicrosoftTermsAccepted "0"','IfSilent 0 +3','SetErrorLevel 2','Abort']
    result=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert output.is_file() and output.read_bytes()[:2]==b'MZ'
    assert 'warning ' not in result.stdout.lower()+result.stderr.lower()
