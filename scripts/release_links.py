"""Validate public release-link metadata; no network, application or model calls."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def validate(value):
    allowed = {'schema','repository','version','tag','source_commit','release_url','download_url','install_url',
        'validation_url','demo_url','source_status','platforms','publication_verified','development_checkpoint_notice',
        'quick_start_url','manifest_url','checksums_url'}
    if set(value) != allowed or value['schema'] != 'litrev.public-release-links.v1':
        raise ValueError('Use the bounded published release-link record.')
    if value['repository'] != 'hnt119/lit-rev-engine' or not re.fullmatch(r'\d+\.\d+\.\d+-beta\.\d+', value['version']):
        raise ValueError('Use this repository and an explicit beta version.')
    if value['tag'] != 'v'+value['version'] or not re.fullmatch('[a-f0-9]{40}',value['source_commit']):
        raise ValueError('Bind an explicit version tag and full source SHA.')
    base = 'https://github.com/'+value['repository']+'/releases/'
    expected = {'release_url':base+'tag/'+value['tag'],
        'download_url':base+'download/'+value['tag']+'/lit-rev-engine-'+value['version']+'.zip',
        'install_url':base+'download/'+value['tag']+'/INSTALL.md',
        'validation_url':base+'download/'+value['tag']+'/VALIDATION.md',
        'quick_start_url':'https://github.com/'+value['repository']+'/blob/'+value['tag']+'/docs/local_preview.md',
        'manifest_url':base+'download/'+value['tag']+'/lit-rev-engine-'+value['version']+'.manifest.json',
        'checksums_url':base+'download/'+value['tag']+'/lit-rev-engine-'+value['version']+'.SHA256SUMS'}
    if any(value[k] != v for k,v in expected.items()) or value['demo_url'] != 'https://hnt119.github.io/projects/literature-review-engine/#saved-evidence':
        raise ValueError('Use only the exact version-specific public destinations.')
    if value['publication_verified'] is not True or value['source_status'] != 'setup_required' or type(value['development_checkpoint_notice']) is not bool:
        raise ValueError('Do not advertise an unpublished artifact or native installer.')
    if set(value['platforms']) != {'macos_arm64_source','windows_x64_source','macos_arm64_desktop','windows_x64_desktop'}:
        raise ValueError('Keep an explicit OS and source-versus-desktop matrix.')
    if any(v not in {'tested','not_available','private_prototype','preview'} for v in value['platforms'].values()):
        raise ValueError('Use an observed platform state.')
    return value

def block(value):
    v=validate(value)
    # The primary action is a readable fallback, while exact source bytes and
    # offline documentation remain explicit secondary downloads.
    result = ('**[Download — source beta '+v['version']+']('+v['release_url']+') · [Quick start]('+v['quick_start_url']+') · [Read-only demo]('+v['demo_url']+')**'
        '\n\n[Direct source ZIP]('+v['download_url']+') · [Manifest]('+v['manifest_url']+') · [SHA-256 checksums]('+v['checksums_url']+') · [Download installation guide]('+v['install_url']+')')
    if v['development_checkpoint_notice']:
        result += '\n\nThis checkout develops the excerpt-first successor. The verified download above contains the earlier interface; its validation record identifies its exact source. Release links update only after publication.'
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--metadata',type=Path,default=ROOT/'config/public_release.json');p.add_argument('--check-readme',action='store_true');p.add_argument('--write-readme',action='store_true');a=p.parse_args()
    value=validate(json.loads(a.metadata.read_text()));wanted=block(value);readme=ROOT/'README.md';text=readme.read_text()
    expression=r'(?<=<!-- published-release:start -->)\n.*?\n(?=<!-- published-release:end -->)'
    match=re.search(expression,text,re.S)
    if not match:raise SystemExit('README release-link markers are missing.')
    if a.write_readme:readme.write_text(re.sub(expression,'\n'+wanted+'\n',text,flags=re.S))
    elif a.check_readme and match.group().strip()!=wanted:raise SystemExit('README and verified release metadata differ.')
    print('Published release-link record and README binding validated; live publication evidence is a separate release-owner check.')

if __name__=='__main__':main()
