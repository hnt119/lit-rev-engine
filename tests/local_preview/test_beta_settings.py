"""Private opt-in configuration; mocks only, no network, models or user data."""
import argparse
import builtins
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_local_beta as check
from scripts import local_beta_settings as settings
from scripts import local_preview as preview
from scripts.run_web import LocalLaunchError


def config(**sections):
    return {'schema': settings.SCHEMA, **sections}


def private_file(tmp_path, value):
    target=tmp_path/'settings.json'
    target.write_text(value if isinstance(value,str) else json.dumps(value))
    target.chmod(0o600)
    return target


def arguments(path=None, **updates):
    return argparse.Namespace(config=path, allow_live=False, api_port=8871, web_port=3088,
                              browser_host='localhost', **updates)


def model():
    return {'enabled':True,'url':'http://127.0.0.1:8000/v1/chat/completions',
            'model':'synthetic-model','model_revision':'synthetic-revision'}


def test_default_sample_is_valid_and_all_optional_capabilities_are_off(tmp_path):
    root=Path(__file__).resolve().parents[2]
    actual=settings.validate_settings(json.loads((root/'config/local-beta.example.json').read_text()),root)
    assert all(actual[feature]['enabled'] is False for feature in settings.FEATURES)
    assert settings.load_settings(None,root)==settings.validate_settings(config(),root)
    env=settings.feature_environment(actual)
    assert {env[key] for key in ('MVP_MAP_ENABLED','MVP_SEARCH_PLANNER_ENABLED','MVP_PROPOSALS_ENABLED')}=={'0'}
    assert 'NCBI_EMAIL' not in env and 'HF_HUB_CACHE' not in env
    assert env['HF_HUB_OFFLINE']==env['TRANSFORMERS_OFFLINE']=='1'


@pytest.mark.parametrize('value', [
    {}, {'schema':'other'}, config(OPENAI_API_KEY='synthetic'), config(maps={'enabled':1}),
    config(maps={'enabled':True,'MVP_MAP_ENABLED':'1'}),
    config(search_planner={**model(),'spend_cap_usd':1}),
    config(live={'enabled':True}), config(live={'enabled':True,'email':'bad'}),
    config(live={'api_key':'bad key'}), config(search_planner={'enabled':True}),
    config(search_planner={**model(),'model':'bad\nvalue'}),
    config(cell_proposals={**model(),'model_revision':'\ud800'}),
])
def test_unknown_or_unsafe_settings_are_rejected_without_values(tmp_path,value):
    with pytest.raises(LocalLaunchError) as error:
        settings.validate_settings(value,tmp_path/'app')
    assert 'bad\nvalue' not in str(error.value) and 'synthetic-model' not in str(error.value)


@pytest.mark.parametrize('url', ['https://127.0.0.1:8000/v1/chat/completions',
    'http://localhost:8000/v1/chat/completions','http://example.invalid:8000/v1/chat/completions',
    'http://127.0.0.1/v1/chat/completions','http://127.0.0.1:0/v1/chat/completions',
    'http://user:pass@127.0.0.1:8000/v1/chat/completions',
    'http://127.0.0.1:8000/v1/chat/completions?key=synthetic',
    'http://127.0.0.1:8000/other','http://127.0.0.1:8000/v1/chat/completions#fragment'])
def test_only_existing_literal_loopback_adapter_endpoint_is_supported(tmp_path,url):
    with pytest.raises(LocalLaunchError,match='literal HTTP loopback'):
        settings.validate_settings(config(cell_proposals={**model(),'url':url}),tmp_path/'app')


def test_valid_external_private_file_is_read_without_forwarding_disabled_values(tmp_path):
    value=config(live={'enabled':False,'email':'reviewer@example.invalid','api_key':'a'*32},
                 maps={'enabled':False,'cache_dir':str(tmp_path/'model-cache')})
    path=private_file(tmp_path,value)
    normalized=settings.load_settings(path,tmp_path/'app')
    env=settings.feature_environment(normalized)
    assert 'NCBI_EMAIL' not in env and 'NCBI_API_KEY' not in env and 'HF_HUB_CACHE' not in env


@pytest.mark.parametrize('raw', ['{"schema":"litrev.local-beta.settings.v1","schema":"litrev.local-beta.settings.v1"}',
                                '{"schema":"litrev.local-beta.settings.v1","maps":{"enabled":NaN}}',
                                '{not json}', '['*1200])
def test_duplicate_malformed_and_unbounded_json_is_rejected(tmp_path,raw):
    with pytest.raises(LocalLaunchError,match='valid private JSON'):
        settings.load_settings(private_file(tmp_path,raw),tmp_path/'app')


def test_private_file_permissions_size_symlinks_and_application_containment(tmp_path):
    root=tmp_path/'app';root.mkdir()
    path=private_file(tmp_path,config())
    path.chmod(0o644)
    with pytest.raises(LocalLaunchError,match='0600'):settings.load_settings(path,root)
    path.chmod(0o600);path.write_text(' '*(settings.MAX_SETTINGS_BYTES+1))
    with pytest.raises(LocalLaunchError,match='16 KiB'):settings.load_settings(path,root)
    path.write_text(json.dumps(config()))
    link=tmp_path/'link.json';link.symlink_to(path)
    with pytest.raises(LocalLaunchError,match='symlink'):settings.load_settings(link,root)
    linked_dir=tmp_path/'linked';linked_dir.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(LocalLaunchError,match='symlink'):settings.load_settings(linked_dir/'settings.json',root)
    inside=root/'settings.json';inside.write_text(path.read_text());inside.chmod(0o600)
    for value in (inside, Path('settings.json'),tmp_path/'outside/../settings.json'):
        with pytest.raises(LocalLaunchError,match='absolute private settings path'):settings.load_settings(value,root)
    with pytest.raises(LocalLaunchError,match='ordinary'):settings.load_settings(tmp_path,root)
    fifo=tmp_path/'settings.fifo';os.mkfifo(fifo,0o600)
    with pytest.raises(LocalLaunchError,match='ordinary'):settings.load_settings(fifo,root)


def test_explicit_opt_ins_survive_clean_environment_without_hosted_or_provider_leak(tmp_path,monkeypatch):
    root=tmp_path/'app';root.mkdir();monkeypatch.setattr(preview,'ROOT',root)
    monkeypatch.setenv('MVP_DEPLOYMENT_MODE','hosted')
    for key in ('OPENAI_API_KEY','HF_TOKEN','DEEPINFRA_API_KEY','MVP_PUBLIC_ORIGIN','HTTPS_PROXY',
                'MVP_PROPOSALS_SPEND_CAP_USD','MVP_SEARCH_PLANNER_SPEND_CAP_USD','NCBI_EMAIL'):
        monkeypatch.setenv(key,'must-not-leak')
    value=config(live={'enabled':True,'email':'reviewer@example.invalid','api_key':'a'*32},
                 maps={'enabled':True,'cache_dir':str(tmp_path/'external-model-cache')},
                 search_planner=model(),cell_proposals=model())
    path=private_file(tmp_path,value)
    env=preview.configured_environment(arguments(path),os.sys.executable,tmp_path/'data')
    assert 'must-not-leak' not in env.values()
    assert env['MVP_DEPLOYMENT_MODE']=='local' and env['NODE_ENV']=='production'
    assert env['MVP_API_ORIGIN']=='http://127.0.0.1:8871' and env['MVP_WEB_ORIGIN']=='http://localhost:3088'
    assert env['NCBI_EMAIL']=='reviewer@example.invalid' and env['NCBI_API_KEY']=='a'*32
    assert env['HF_HUB_CACHE']==str(tmp_path/'external-model-cache')
    for prefix in ('MVP_SEARCH_PLANNER','MVP_PROPOSALS'):
        assert env[prefix+'_ENABLED']=='1' and env[prefix+'_SPEND_CAP_USD']=='0'
        assert env[prefix+'_MODEL']=='synthetic-model'
    assert env['MVP_MAP_ENABLED']==env['HF_HUB_OFFLINE']==env['TRANSFORMERS_OFFLINE']=='1'
    assert not set(env)&{'OPENAI_API_KEY','DEEPINFRA_API_KEY','HF_TOKEN','MVP_PUBLIC_ORIGIN','HTTPS_PROXY'}
    args=arguments(path);args.allow_live=True
    with pytest.raises(LocalLaunchError,match='not both'):
        preview.configured_environment(args,os.sys.executable,tmp_path/'data')


def test_no_config_keeps_legacy_live_opt_in_and_disables_inherited_features(tmp_path,monkeypatch):
    monkeypatch.setenv('NCBI_EMAIL','reviewer@example.invalid')
    monkeypatch.setenv('MVP_MAP_ENABLED','1')
    env=preview.configured_environment(arguments(),os.sys.executable,tmp_path/'data')
    assert env['MVP_MAP_ENABLED']=='0' and 'NCBI_EMAIL' not in env
    args=arguments();args.allow_live=True
    env=preview.configured_environment(args,os.sys.executable,tmp_path/'data')
    assert env['NCBI_EMAIL']=='reviewer@example.invalid' and env['MVP_MAP_ENABLED']=='0'


def test_map_cache_is_external_absolute_and_never_changes_pinned_profile(tmp_path):
    root=tmp_path/'app';root.mkdir()
    for path in ('relative',str(root/'weights'),str(tmp_path/'outside/../app/weights')):
        with pytest.raises(LocalLaunchError,match='absolute external'):
            settings.validate_settings(config(maps={'enabled':True,'cache_dir':path}),root)
    normalized=settings.validate_settings(config(maps={'enabled':True}),root)
    assert settings.feature_environment(normalized)['MVP_MAP_ENABLED']=='1'
    assert 'HF_HUB_CACHE' not in settings.feature_environment(normalized)


def test_check_config_only_constructs_existing_adapters_and_does_not_call_them(tmp_path,monkeypatch):
    from src.mvp.adapters.cell_generation import ConfiguredCellGenerationAdapter
    from src.mvp.adapters.search_planning import ConfiguredSearchPlanningAdapter
    monkeypatch.setattr(ConfiguredCellGenerationAdapter,'generate',lambda *a,**k:pytest.fail('No generation'))
    monkeypatch.setattr(ConfiguredSearchPlanningAdapter,'propose',lambda *a,**k:pytest.fail('No planning'))
    env=settings.feature_environment(settings.validate_settings(config(search_planner=model(),cell_proposals=model()),tmp_path/'app'))
    original_import=builtins.__import__
    def no_optional(name,*args,**kwargs):
        if name in {'sentence_transformers','torch','src.mvp.adapters.paper_embeddings'}:
            pytest.fail('Disabled map check must not import mapping/model stack')
        return original_import(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',no_optional)
    report,code=check.inspect_configuration(env)
    assert code==0 and report['status']=='CONFIGURATION_INSPECTED'
    assert report['model_calls']==report['provider_calls']==report['downloads']==0
    for key in ('search_planner','cell_proposals'):
        assert report['capabilities'][key]['enabled'] is True
        assert report['capabilities'][key]['real_inference']=='NOT_RUN'
    assert report['capabilities']['new_maps']['enabled'] is False


def test_missing_optional_map_setup_is_reported_without_loading_weights(tmp_path,monkeypatch):
    from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder
    monkeypatch.setattr(LocalPaperEmbedder,'readiness',lambda self:(False,'Setup required: synthetic missing optional dependencies.'))
    monkeypatch.setattr(LocalPaperEmbedder,'_load',lambda *a:pytest.fail('No model loading'))
    report,code=check.inspect_configuration({'MVP_MAP_ENABLED':'1','HF_HUB_CACHE':str(tmp_path/'cache')})
    assert code==2 and report['capabilities']['new_maps']['setup_ready'] is False
    assert report['capabilities']['new_maps']['real_model_check']=='NOT_RUN'
    assert not (tmp_path/'cache').exists()


@pytest.mark.parametrize('with_maps',[False,True])
def test_optional_map_dependency_install_requires_explicit_setup_flag(tmp_path,monkeypatch,with_maps):
    root=tmp_path/'app';(root/'apps/web').mkdir(parents=True);monkeypatch.setattr(preview,'ROOT',root)
    monkeypatch.setattr(preview,'validate_distribution_license',lambda path:{})
    monkeypatch.setattr(preview,'prerequisites',lambda *a,**k:{'node':'synthetic-node','pnpm':'synthetic-pnpm'})
    monkeypatch.setattr(preview,'fingerprint',lambda path:'synthetic-fingerprint')
    class Builder:
        def __init__(self,**kwargs):pass
        def create(self,path):path.mkdir();(path/'bin').mkdir();(path/'bin/python').write_text('synthetic')
    monkeypatch.setattr(preview.venv,'EnvBuilder',Builder)
    calls=[]
    def execute(command,**kwargs):calls.append((command,kwargs));return SimpleNamespace(returncode=0)
    monkeypatch.setattr(preview.subprocess,'run',execute)
    result=preview.setup(argparse.Namespace(node=None,pnpm=None,with_maps=with_maps))
    command=calls[0][0]
    assert ('requirements-map.txt' in command) is with_maps
    assert command[:4]==[str(root/preview.VENV/'bin/python'),'-m','pip','install']
    assert calls[-1][0]==['synthetic-pnpm','build']
    assert all(item[1]['env']['MVP_MAP_ENABLED']=='0' for item in calls)
    assert result['optional_map_dependencies'] is with_maps and result['model_downloads']==0
    assert not (tmp_path/'data').exists()


@pytest.mark.parametrize('with_retrieval',[False,True])
def test_retrieval_runtime_install_requires_explicit_setup_flag(tmp_path,monkeypatch,with_retrieval):
    import argparse
    from scripts import local_preview as preview
    monkeypatch.setattr(preview,'ROOT',tmp_path)
    monkeypatch.setattr(preview,'validate_distribution_license',lambda root:None)
    monkeypatch.setattr(preview,'prerequisites',lambda *a:{'node':'node','pnpm':'pnpm'})
    monkeypatch.setattr(preview,'reject_web_env_files',lambda root:None)
    monkeypatch.setattr(preview,'fingerprint',lambda path:'synthetic-fingerprint')
    def create(target):
        (target/'bin').mkdir(parents=True);(target/'bin/python').write_text('synthetic')
    monkeypatch.setattr(preview.venv.EnvBuilder,'create',lambda self,target:create(target))
    commands=[]
    monkeypatch.setattr(preview.subprocess,'run',lambda command,**kw:commands.append(command) or type('Result',(),{'returncode':0})())
    result=preview.setup(argparse.Namespace(node=None,pnpm=None,with_maps=False,with_retrieval=with_retrieval))
    assert ('requirements-retrieval.txt' in commands[0]) is with_retrieval
    assert all('retrieval_pack.py' not in command for command in commands)
    assert result['optional_retrieval_dependencies'] is with_retrieval and result['model_downloads']==0
