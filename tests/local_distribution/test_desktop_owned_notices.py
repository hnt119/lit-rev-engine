"""Project-owned compatibility is proved separately from unresolved upstream licensing."""
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest
from scripts.desktop_notices import copy_web_dependency_notices

ROOT=Path(__file__).resolve().parents[2]


def tree(tmp_path):
    installed=tmp_path/'installed';installed.mkdir()
    bundled=tmp_path/'standalone/node_modules/client-only';bundled.mkdir(parents=True)
    own=tmp_path/'owned';shutil.copytree(ROOT/'apps/desktop/client-boundary',own)
    for p in own.iterdir():shutil.copy2(p,bundled/p.name)
    return installed,bundled,own


def test_own_component_retains_own_notice_and_exact_source_without_upstream_invention(tmp_path):
    installed,bundle,own=tree(tmp_path)
    result=copy_web_dependency_notices(bundle.parents[1],installed,tmp_path/'notices',project_component_root=own)
    entry=result['packages'][0]
    assert entry['name']=='@hnt119/litrev-client-boundary'
    assert entry['notice_status']=='retained_project_owned_compatibility_component'
    assert result['missing_notice_sources']==[]
    assert 'client-only' not in [e['name'] for e in result['packages']]
    assert 'removed upstream' in entry['project_owned_source']['scope']
    assert entry['notice_files'][0]['kind']=='project_engine_license'
    assert (tmp_path/'notices'/entry['notice_files'][0]['file']).read_bytes()==(ROOT/'LICENSE').read_bytes()
    assert result['public_distribution_gates']['qualified'] is False


@pytest.mark.parametrize('change',['code','license','extra','identity','link'])
def test_replacement_is_not_accepted_by_name_alone(tmp_path,change):
    installed,bundle,own=tree(tmp_path)
    if change=='code':(bundle/'index.js').write_text('changed')
    elif change=='license':(bundle/'LICENSE').write_text('not the owner license')
    elif change=='extra':(bundle/'unreviewed.js').write_text('extra')
    elif change=='identity':
        data=json.loads((bundle/'package.json').read_text());data['version']='0.2.0';(bundle/'package.json').write_text(json.dumps(data))
    else:
        (bundle/'index.js').unlink();(bundle/'index.js').symlink_to(own/'index.js')
    with pytest.raises(ValueError):copy_web_dependency_notices(bundle.parents[1],installed,tmp_path/'notices',project_component_root=own)
    assert not (tmp_path/'notices').exists()
