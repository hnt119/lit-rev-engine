"""Local, session-owned preferences and ephemeral credentials.

This is deliberately not a research database or a credential vault. Opening or
saving configuration never contacts a provider. No process environment is edited.
"""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from src.platform_support import atomic_replace
from src.platform_support import private_directory, open_private, owned_path, assert_no_links
from pathlib import Path
import re
import secrets
import stat
from threading import RLock, BoundedSemaphore
from typing import Literal

from pydantic import Field, model_validator
from src.mvp.contracts import Model, canonical, digest, now
from src.mvp.ports import MvpError


class PubMedPreferences(Model):
    enabled: bool = False
    email: str = Field(default='', max_length=254)

    @model_validator(mode='after')
    def valid(self):
        if self.email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', self.email):
            raise ValueError('Supply a valid contact email')
        if self.enabled and not self.email:
            raise ValueError('PubMed needs a contact email; its API key is optional')
        return self


class AIPreferences(Model):
    provider: Literal['none', 'local', 'openai', 'deepseek'] = 'none'
    model: str = Field(default='', max_length=200)
    model_revision: str = Field(default='', max_length=200)
    local_url: str = Field(default='http://127.0.0.1:8080/v1/chat/completions', max_length=500)
    planning_enabled: bool = False
    proposals_enabled: bool = False

    @model_validator(mode='after')
    def valid(self):
        if any(ord(c) < 32 or ord(c) == 127 for c in self.model + self.model_revision):
            raise ValueError('Use a plain model identifier and revision')
        if self.provider != 'none' and (not self.model.strip() or not self.model_revision.strip()):
            raise ValueError('Set the explicit model and revision/profile version')
        if self.provider == 'local':
            from src.mvp.adapters.search_planning import ConfiguredSearchPlanningAdapter
            ConfiguredSearchPlanningAdapter(enabled=True, url=self.local_url,
                model=self.model, model_revision=self.model_revision)
        else:
            # Even an inactive local URL is a non-secret preference. Reject
            # credential-bearing/remote values rather than save them for later.
            from src.mvp.adapters.search_planning import ConfiguredSearchPlanningAdapter
            ConfiguredSearchPlanningAdapter(enabled=True, url=self.local_url,
                model='configuration-validation', model_revision='configuration.v1')
        if self.provider == 'none' and (self.planning_enabled or self.proposals_enabled):
            raise ValueError('Choose a provider before enabling AI assistance')
        return self


class SearchDefaults(Model):
    max_results: int = Field(default=30, ge=1, le=50, strict=True)
    sort: Literal['relevance', 'pub_date'] = 'relevance'


class MapPreferences(Model):
    cache_dir: str = Field(default='', max_length=1000)


class RetrievalPreferences(Model):
    # Default affects future explicit operations; saved definitions retain profiles.
    profile_id: Literal['legacy_block_prefix_v1', 'lexical_spans_v1',
        'hybrid_qwen3_06b_rrf_rerank_v1', 'hybrid_medcpt_passage_rrf_rerank_v1'] = 'legacy_block_prefix_v1'
    device: Literal['cpu', 'mps'] = 'cpu'


class RuntimePreferences(Model):
    pubmed: PubMedPreferences = Field(default_factory=PubMedPreferences)
    ai: AIPreferences = Field(default_factory=AIPreferences)
    defaults: SearchDefaults = Field(default_factory=SearchDefaults)
    maps: MapPreferences = Field(default_factory=MapPreferences)
    retrieval: RetrievalPreferences = Field(default_factory=RetrievalPreferences)


class SettingsPut(Model):
    expected_revision: int = Field(ge=0, strict=True)
    preferences: RuntimePreferences
    ncbi_api_key: str | None = Field(default=None, max_length=512)
    ai_api_key: str | None = Field(default=None, max_length=512)


class SettingsTest(Model):
    expected_revision: int = Field(ge=0, strict=True)


class DesktopOnboarding(Model):
    """Non-secret UI progress; never a provider or research-readiness judgment."""
    schema_version: Literal['desktop-onboarding.v1'] = 'desktop-onboarding.v1'
    revision: int = Field(default=0, ge=0, strict=True)
    step: Literal['welcome', 'sources', 'retrieval', 'ai', 'ready'] = 'welcome'
    completed: bool = Field(default=False, strict=True)


class DesktopOnboardingPut(Model):
    expected_revision: int = Field(ge=0, strict=True)
    step: Literal['welcome', 'sources', 'retrieval', 'ai', 'ready']
    completed: bool = Field(strict=True)


class RuntimeSettings:
    def __init__(self, directory, *, clock=None):
        self.directory = Path(directory).expanduser().absolute() / 'session-settings'
        try: private_directory(self.directory)
        except (OSError, ValueError):
            raise MvpError('settings_storage', 'Use a private owned settings directory without links.') from None
        self._lock = RLock()
        self._secrets, self._tests, self._permits = {}, {}, {}
        # All settings revisions and sessions share this single outbound slot.
        self._generation_slot = BoundedSemaphore(1)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _path(self, owner):
        if not re.fullmatch('[a-f0-9]{64}', owner):
            raise MvpError('session_unavailable', 'The session is unavailable.')
        return self.directory / (owner + '.json')

    def _read(self, owner):
        path = self._path(owner)
        if not path.exists():
            return {'revision': 0, 'configured': False, 'preferences': RuntimePreferences().model_dump(mode='json')}
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or not owned_path(path, private=True) or info.st_size > 16384:
            raise MvpError('settings_storage', 'Private settings metadata is unsafe; it was not opened.')
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            fields = {'revision', 'configured', 'preferences'}
            if set(value) not in (fields, fields | {'onboarding'}):
                raise ValueError('unsupported settings fields')
            value['preferences'] = RuntimePreferences.model_validate(value['preferences']).model_dump(mode='json')
            # Welcome progress is validated by its own projection. A damaged
            # optional progress record must not disable valid Core settings.
            # An onboarding-only write must not activate otherwise unsaved
            # defaults or import operator credentials. Existing records retain
            # their original strict configured/revision contract.
            untouched = (value.get('configured') is False and value.get('revision') == 0
                         and 'onboarding' in value
                         and value['preferences'] == RuntimePreferences().model_dump(mode='json'))
            configured = (value.get('configured') is True and type(value.get('revision')) is int
                          and value['revision'] >= 1)
            if type(value.get('revision')) is not int or not (untouched or configured):
                raise ValueError('invalid revision')
            return value
        except (ValueError, KeyError, TypeError):
            raise MvpError('settings_storage', 'Private settings metadata is invalid; no provider was selected.') from None

    def get(self, owner):
        with self._lock:
            value = self._read(owner)
            keys = self._secrets.get(owner, {})
            pref = value['preferences']
            tests = self._tests.get(owner, {})
            def status(kind, enabled):
                old = tests.get(kind)
                if old and old['revision'] == value['revision']:
                    return {k: v for k, v in old.items() if k != 'revision'}
                return {'state': 'Not tested' if enabled else 'Disabled', 'tested_at': None,
                        'message': 'Configuration valid; no connection has been tested.' if enabled else 'Manual research remains available.'}
            ai_enabled = pref['ai']['provider'] != 'none'
            result = deepcopy(value)
            result.pop('onboarding', None)  # Keep the existing settings projection unchanged.
            result.update(schema_version='runtime-settings.v1', credentials={k: bool(keys.get(k)) for k in ('ncbi_api_key', 'ai_api_key')},
                status={'pubmed': status('pubmed', pref['pubmed']['enabled']), 'ai': status('ai', ai_enabled),
                        'maps': {'state': 'Operator configuration',
                                 'message': 'Saved cache preference is inactive. Set maps.cache_dir in the existing private --config launch file and restart to apply it. No models are downloaded or maps refitted by Settings.'}},
                operator_configuration='unchanged')
            if ai_enabled and pref['ai']['provider'] in {'openai', 'deepseek'} and not keys.get('ai_api_key'):
                result['status']['ai'] = {'state': 'Configuration valid', 'tested_at': None,
                    'message': 'Enter a session key before cloud use. Credentials are cleared on backend restart.'}
            if not value['configured']:
                for kind in ('pubmed', 'ai'):
                    result['status'][kind] = {'state': 'Operator configuration', 'tested_at': None,
                        'message': 'Existing private launch configuration remains effective. These unsaved session defaults do not describe or import its credentials. Saving Settings explicitly selects session configuration.'}
            return result

    def put(self, owner, request):
        with self._lock:
            previous = self._read(owner)
            if previous['revision'] != request.expected_revision:
                raise MvpError('stale_settings', 'Settings changed in another tab. Keep edits and reload before saving.')
            keys = dict(self._secrets.get(owner, {}))
            if previous['preferences']['ai']['provider'] != request.preferences.ai.provider:
                keys.pop('ai_api_key', None)
            for name in ('ncbi_api_key', 'ai_api_key'):
                if name in request.model_fields_set:
                    value = getattr(request, name)
                    if value and (not value.strip() or any(ord(c) < 33 or ord(c) > 126 for c in value)):
                        raise MvpError('settings_key', 'Use the provider key without spaces or control characters.')
                    if value: keys[name] = value
                    else: keys.pop(name, None)
            value = {'revision': previous['revision'] + 1, 'configured': True,
                     'preferences': request.preferences.model_dump(mode='json')}
            if 'onboarding' in previous:
                value['onboarding'] = deepcopy(previous['onboarding'])
            self._write(owner, value)
            self._secrets[owner] = keys
            self._tests.pop(owner, None)
            return self.get(owner)

    def _write(self, owner, value):
        # Both configuration and UI progress use this same bounded private
        # store and lock. Their independent revisions do not authorize each other.
        path = self._path(owner)
        temporary = path.with_suffix('.new-' + secrets.token_hex(8))
        fd = open_private(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(canonical(value) + '\n'); stream.flush(); os.fsync(stream.fileno())
            atomic_replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _progress(value):
        try:
            progress = DesktopOnboarding.model_validate(value.get('onboarding', {}))
            if 'onboarding' in value and progress.revision < 1:
                raise ValueError('invalid onboarding revision')
            return progress
        except (ValueError, TypeError):
            raise MvpError('onboarding_storage', 'Saved welcome progress is invalid. Core research remains available; no configuration or research records were reset.') from None

    def get_onboarding(self, owner):
        with self._lock:
            return self._progress(self._read(owner)).model_dump(mode='json')

    def put_onboarding(self, owner, request):
        with self._lock:
            value = self._read(owner)
            previous = self._progress(value)
            if previous.revision != request.expected_revision:
                raise MvpError('stale_onboarding', 'Welcome setup changed in another window. Reload the saved progress before continuing; research drafts are retained.')
            if request.completed and not previous.completed and request.step != 'ready':
                raise MvpError('onboarding_state', 'Finish the welcome flow from its final step. This does not mark optional features ready.')
            progress = DesktopOnboarding(revision=previous.revision + 1, step=request.step,
                                         completed=previous.completed or request.completed)
            value['onboarding'] = progress.model_dump(mode='json')
            self._write(owner, value)
            # No credentials, test observations, consent, configuration revision,
            # research records, provider requests or model work are changed.
            return progress.model_dump(mode='json')

    def snapshot(self, owner, expected=None):
        with self._lock:
            value = self._read(owner)
            if expected is not None and value['revision'] != expected:
                raise MvpError('stale_settings', 'Settings changed. Review the current configuration before this operation.')
            snapshot = deepcopy(value)
            snapshot.pop('onboarding', None)
            return snapshot, dict(self._secrets.get(owner, {}))

    def assert_current(self, owner, revision):
        self.snapshot(owner, revision)

    def record_test(self, owner, revision, kind, success):
        with self._lock:
            self.assert_current(owner, revision)
            self._tests.setdefault(owner, {})[kind] = dict(revision=revision,
                state='Last test succeeded' if success else 'Failed', tested_at=now(),
                message='The explicit bounded connection test succeeded.' if success else 'The connection test failed; no fallback was attempted.')
            return self.get(owner)

    def prepare(self, owner, revision, binding, disclosure, *, packet_hashes=None):
        with self._lock:
            self.assert_current(owner, revision)
            # Bound pending consent storage, without storing credentials or packet text.
            self._permits = {k: v for k, v in self._permits.items() if v['expires'] > self.clock()}
            if len(self._permits) >= 256:
                raise MvpError('consent_limit', 'Too many pending authorizations; wait for them to expire.')
            identifier, expires = secrets.token_urlsafe(32), self.clock() + timedelta(minutes=5)
            self._permits[identifier] = dict(owner=owner, revision=revision, binding=digest(binding), expires=expires,
                state='ready', packet_hashes=deepcopy(packet_hashes))
            return {**disclosure, 'consent_id': identifier, 'settings_revision': revision, 'expires_at': expires.isoformat()}

    def consume(self, owner, revision, identifier, binding):
        with self._lock:
            self.assert_current(owner, revision)
            item = self._permits.get(identifier or '')
            if not item or item['owner'] != owner or item['revision'] != revision or item['binding'] != digest(binding) or item['expires'] <= self.clock():
                raise MvpError('generation_consent', 'Review and explicitly authorize this exact bounded operation again.')
            if item['state'] != 'ready':
                raise MvpError('generation_already_attempted', 'This authorization was already attempted. Reopen its retained run or explicitly authorize a new attempt; no new call was made.')
            item['state'] = 'consumed'
            return deepcopy(item['packet_hashes'])

    @contextmanager
    def generation_slot(self):
        if not self._generation_slot.acquire(blocking=False):
            raise MvpError('generation_busy', 'Another session has an active bounded model operation. No new call was made.')
        try:
            yield
        finally:
            self._generation_slot.release()
