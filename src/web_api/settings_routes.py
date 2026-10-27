"""Thin local-only runtime configuration over the existing application adapters."""
from contextlib import contextmanager
from copy import copy
from fastapi import Depends
from src.mvp.ports import MvpError
from src.mvp.contracts import canonical
from .runtime_settings import RuntimeSettings, SettingsPut, SettingsTest, DesktopOnboarding, DesktopOnboardingPut
from pydantic import Field
from src.mvp.search_plan_contracts import ProposeSearchPlanRequest
from src.mvp.proposal_contracts import ProposalGenerateRequest


class RuntimePlanRequest(ProposeSearchPlanRequest):
    settings_revision: int | None = Field(default=None, ge=0, strict=True)
    consent_id: str | None = Field(default=None, max_length=100)


class RuntimeProposalRequest(ProposalGenerateRequest):
    settings_revision: int | None = Field(default=None, ge=0, strict=True)
    consent_id: str | None = Field(default=None, max_length=100)


def core_request(request, model):
    return model.model_validate(request.model_dump(exclude={'settings_revision', 'consent_id'}, mode='json'))


class DisabledDiscovery:
    def search(self, _request):
        raise MvpError('live_not_configured', 'Enable PubMed and supply a contact email in Research & AI Settings. An NCBI API key is optional.')


class RuntimeBoundAdapter:
    """Immutable adapter snapshot with a short revision publication barrier."""
    def __init__(self, adapter, settings, owner, revision, provider):
        self.wrapped, self.settings, self.owner = adapter, settings, owner
        self.revision, self.provider = revision, provider
        self.enabled = adapter.enabled
        self.expected_packet_hashes = None
        self.prompt_version = adapter.prompt_version
        self.max_call_seconds = getattr(adapter, 'max_call_seconds', 10)
        profile = adapter.profile
        if hasattr(profile, 'model_dump'): profile = profile.model_dump(mode='json')
        self.profile = {**profile, 'settings_revision': revision, 'provider': provider} if profile else None
        if hasattr(adapter, 'still_current'): adapter.still_current = self.validate_current

    def validate_current(self):
        self.settings.assert_current(self.owner, self.revision)

    @contextmanager
    def publication_guard(self):
        with self.settings._lock:
            self.validate_current()
            yield

    def capability(self):
        result = self.wrapped.capability()
        return result.model_copy(update={'model_profile': self.profile, 'provider': self.provider,
            'settings_revision': self.revision, 'paid_calls': self.provider in {'openai', 'deepseek'},
            'max_runtime_seconds': self.max_call_seconds,
            **({'reason': 'Re-enter the session key in Settings; credentials are cleared after backend restart.'} if getattr(self.wrapped, '_missing_key', False) else {})})

    def propose(self, question, *, timeout_seconds):
        self.validate_current()
        result = self.wrapped.propose(question, timeout_seconds=timeout_seconds)
        self.validate_current()
        return result.model_copy(update={'model_profile': self.profile})

    def generate(self, packet, *, timeout_seconds):
        self.validate_current()
        if self.expected_packet_hashes is not None:
            from src.mvp.contracts import digest
            if self.expected_packet_hashes.get(packet.paper_id) != digest(packet_data(packet)):
                raise MvpError('proposal_stale_inputs', 'The exact evidence packet changed after authorization; review it again before any call.')
        result = self.wrapped.generate(packet, timeout_seconds=timeout_seconds)
        self.validate_current()
        return result


def packet_data(packet):
    """Candidate receipt IDs differ per run; exact evidence does not."""
    value = packet.model_dump(mode='json') if hasattr(packet, 'model_dump') else dict(packet)
    value['fields'] = [{k: v for k, v in f.items() if k != 'candidate_run_id'} for f in value['fields']]
    return value


def configured_adapter(settings, owner, task, revision=None):
    snapshot, keys = settings.snapshot(owner, revision)
    if not snapshot['configured']: return None, snapshot
    from src.mvp.adapters.cell_generation import ConfiguredCellGenerationAdapter
    from src.mvp.adapters.search_planning import ConfiguredSearchPlanningAdapter
    from src.mvp.adapters.cloud_generation import SessionCloudAdapter
    ai = snapshot['preferences']['ai']
    enabled = ai[task + '_enabled'] and ai['provider'] != 'none'
    cls = ConfiguredSearchPlanningAdapter if task == 'planning' else ConfiguredCellGenerationAdapter
    if not enabled:
        adapter = cls()
    elif ai['provider'] == 'local':
        adapter = cls(enabled=True, url=ai['local_url'], model=ai['model'], model_revision=ai['model_revision'])
    else:
        if not keys.get('ai_api_key'):
            adapter = cls()
            adapter._missing_key = True
        else:
            adapter = SessionCloudAdapter(provider=ai['provider'], model=ai['model'], model_revision=ai['model_revision'],
                key=keys['ai_api_key'], task=task, settings_revision=snapshot['revision'],
                still_current=lambda: settings.assert_current(owner, snapshot['revision']))
    return RuntimeBoundAdapter(adapter, settings, owner, snapshot['revision'], ai['provider']), snapshot


def engine_for(settings, owner, mode, engine):
    snapshot, keys = settings.snapshot(owner)
    if not snapshot['configured'] or mode != 'live': return engine
    from src.mvp.adapters.pubmed import PubMedPreviewProvider
    pref = snapshot['preferences']['pubmed']
    result = copy(engine)
    result._discovery = (PubMedPreviewProvider(email=pref['email'], api_key=keys.get('ncbi_api_key'))
                         if pref['enabled'] else DisabledDiscovery())
    result._discovery.configuration_profile = {'provider': 'pubmed', 'settings_revision': snapshot['revision'],
        'adapter': 'pubmed-esearch-efetch.v1', 'api_key_supplied': bool(keys.get('ncbi_api_key'))}
    return result


def disclosure(adapter, task, data, calls):
    profile = adapter.profile or {}
    cloud = adapter.provider in {'openai', 'deepseek'}
    encoded = canonical(data).encode('utf-8')
    return dict(provider=adapter.provider, model=profile.get('model'), task=task,
        data_types=['research question'] if task == 'planning' else ['board question', 'paper titles', 'field subquestions', 'bounded retained source excerpts and citation anchors'],
        input_characters=len(canonical(data)), input_bytes=len(encoded), max_calls=calls,
        max_output_tokens=profile.get('max_output_tokens', 4096 if task == 'planning' else 2048),
        timeout_seconds=30 if task == 'planning' and cloud else 35 if task == 'proposals' else 10,
        cost_estimate='Unavailable; user account may be charged. Limits are not a guaranteed dollar cap.' if cloud else 'Local server cost unknown; no application cloud billing.',
        packet_scope='Only the displayed operation\'s bounded context; instructions and JSON framing are additional input.',
        retries=0)


def install_settings_routes(app, *, directory, session_for, dependencies):
    if app.state.deployment.hosted:
        app.state.runtime_settings = None
        return
    settings = RuntimeSettings(directory)
    app.state.runtime_settings = settings

    @app.get('/api/v1/settings', dependencies=dependencies)
    def get(session=Depends(session_for)):
        return settings.get(session['token_hash'])

    @app.put('/api/v1/settings', dependencies=dependencies)
    def put(request: SettingsPut, session=Depends(session_for)):
        return settings.put(session['token_hash'], request)

    def desktop_progress_available():
        if not app.state.desktop_onboarding_ready:
            raise MvpError('unknown_onboarding', 'Welcome setup is available in the managed desktop application.')

    @app.get('/api/v1/settings/onboarding', response_model=DesktopOnboarding, dependencies=dependencies)
    def get_onboarding(session=Depends(session_for)):
        desktop_progress_available()
        return settings.get_onboarding(session['token_hash'])

    @app.put('/api/v1/settings/onboarding', response_model=DesktopOnboarding, dependencies=dependencies)
    def put_onboarding(request: DesktopOnboardingPut, session=Depends(session_for)):
        desktop_progress_available()
        return settings.put_onboarding(session['token_hash'], request)

    @app.post('/api/v1/settings/test-pubmed', dependencies=dependencies)
    def test_pubmed(request: SettingsTest, session=Depends(session_for)):
        from src.mvp.adapters.search_diagnostics import PubMedSearchDiagnostics
        owner = session['token_hash']
        snapshot, keys = settings.snapshot(owner, request.expected_revision)
        pref = snapshot['preferences']['pubmed']
        if not pref['enabled']:
            raise MvpError('live_not_configured', 'Enable PubMed and supply your contact email before the explicit connection test.')
        try:
            diagnostic = PubMedSearchDiagnostics(email=pref['email'], api_key=keys.get('ncbi_api_key'))
            result = diagnostic.check('1[uid]')
            success = result.status == 'succeeded'
        except Exception:
            success = False
        return settings.record_test(owner, snapshot['revision'], 'pubmed', success)
