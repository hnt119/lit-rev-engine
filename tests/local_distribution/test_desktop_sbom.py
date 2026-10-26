"""Inventory reflects payload facts and does not grant distribution clearance."""
import json
import pytest
from scripts.desktop_sbom import collect_payload


def test_actual_node_python_native_and_unknown_metadata_are_retained(tmp_path):
    p=tmp_path/'node_modules/client-only';p.mkdir(parents=True);(p/'package.json').write_text(json.dumps({'name':'client-only','version':'0.0.1','license':'MIT'}));(p/'index.js').write_text('')
    d=tmp_path/'python/lib/site-packages/fixture-1.0.dist-info';d.mkdir(parents=True);(d/'METADATA').write_text('Name: fixture\nVersion: 1.0\nLicense: MIT\nRequires-Dist: dependency\n')
    (d/'LICENSE').write_text('SYNTHETIC notice');(tmp_path/'fixture.dylib').write_bytes(b'SYNTHETIC not a binary')
    bom,review=collect_payload(tmp_path,'a'*40,'darwin-arm64')
    assert bom['bomFormat']=='CycloneDX' and len(bom['components'])==2
    assert review['public_distribution_qualified'] is False
    assert any(x['name']=='client-only' for x in review['notice_review_items'])
    assert review['native_files'][0]['path']=='fixture.dylib'
    assert str(tmp_path) not in json.dumps(bom)+json.dumps(review)


def test_payload_links_cannot_inventory_private_external_files(tmp_path):
    inside=tmp_path/'payload';inside.mkdir();outside=tmp_path/'private';outside.write_text('not allowed');(inside/'link').symlink_to(outside)
    with pytest.raises(ValueError,match='leaves'):collect_payload(inside,'a'*40,'darwin-arm64')


def test_exact_supplemental_python_notice_is_bound_to_name_version_and_bytes(tmp_path):
    from hashlib import sha256
    p=tmp_path/'python/lib/site-packages/tokenizers-0.22.2.dist-info';p.mkdir(parents=True);(p/'METADATA').write_text('Name: tokenizers\nVersion: 0.22.2\nLicense: Apache-2.0\n')
    extra=tmp_path/'python/UPSTREAM_LICENSES/tokenizers-0.22.2';extra.mkdir(parents=True);raw=b'SYNTHETIC exact upstream license';(extra/'LICENSE').write_bytes(raw)
    info={'name':'tokenizers','version':'0.22.2','license_sha256':sha256(raw).hexdigest(),'source_url':'https://example.invalid/source'};(extra/'PROVENANCE.json').write_text(json.dumps(info))
    bom,review=collect_payload(tmp_path,'a'*40,'darwin-arm64');assert review['notice_review_items']==[]
    (extra/'LICENSE').write_bytes(b'changed');_,review=collect_payload(tmp_path,'a'*40,'darwin-arm64');assert review['notice_review_items'][0]['name']=='tokenizers'


def test_structured_vendor_credits_and_python_linkage_are_actual_bound_inputs(tmp_path):
    from hashlib import sha256
    html=tmp_path/'LICENSES.chromium.html'
    html.write_text('<div class="product"><span class="title">Example codec</span><span class="homepage"><a href="https://example.invalid/codec">homepage</a></span><div class="license"><pre>SYNTHETIC LGPL-2.1 corresponding source and relink terms</pre></div></div>')
    notices=tmp_path/'python/UPSTREAM_LICENSES';(notices/'licenses').mkdir(parents=True)
    raw=b'SYNTHETIC retained notice';(notices/'licenses/LICENSE.fixture.txt').write_bytes(raw)
    provenance={'schema':'litrev.python-runtime-license-provenance.v1','python_version':'3.12.15','licenses':['Python-2.0'],
        'license_path':'licenses/LICENSE.fixture.txt','upstream_metadata_sha256':'b'*64,'upstream_archive':{'sha256':'c'*64},
        'retained_notice_files':{'LICENSE.fixture.txt':sha256(raw).hexdigest()},'extensions':{'_fixture':[{'licenses':['MIT'],
        'license_paths':['licenses/LICENSE.fixture.txt'],'links':[{'name':'fixture','path_static':'build/lib/libfixture.a'},{'name':'System','system':True}]}]}}
    (notices/'PYTHON_LICENSE_PROVENANCE.json').write_text(json.dumps(provenance))
    _,review=collect_payload(tmp_path,'a'*40,'darwin-arm64');upstream=review['upstream_component_review']
    vendor=upstream['chromium_credit_components'][0]
    assert vendor['name']=='Example codec' and vendor['version'] is None
    assert vendor['input']['sha256']==sha256(html.read_bytes()).hexdigest()
    assert 'source_offer_or_relink_terms_present' in vendor['review_flags']
    extension=next(v for v in upstream['python_runtime_components'] if v['name']=='CPython extension _fixture')
    assert extension['links'][0]['static'] is True and extension['links'][1]['system'] is True
    assert 'build/lib/' not in json.dumps(review)  # Do not copy upstream build-machine fields.
    assert not any('client-only' in gate or 'libvips' in gate for gate in review['remaining_gates'])
    (notices/'licenses/LICENSE.fixture.txt').write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):collect_payload(tmp_path,'a'*40,'darwin-arm64')


def test_torch_third_party_inventory_is_not_mislabeled_exact_binary_linkage(tmp_path):
    root=tmp_path/'python/lib/site-packages/torch-2.12.0.dist-info';(root/'licenses').mkdir(parents=True)
    (root/'METADATA').write_text('Name: torch\nVersion: 2.12.0\nLicense: BSD-3-Clause\n')
    notice=root/'licenses/LICENSE';notice.write_text('SYNTHETIC main notice\nName: component\nLicense: Apache-2.0 with exception\nFiles: /upstream/build/location\n')
    _,review=collect_payload(tmp_path,'a'*40,'darwin-arm64')
    item=review['upstream_component_review']['torch_declared_components'][0]
    assert item['name']=='component' and item['version'] is None
    assert 'requires upstream mapping' in item['linkage_status']
    assert review['native_distribution_review'][0]['name']=='torch'
    assert '/upstream/build' not in json.dumps(review)
