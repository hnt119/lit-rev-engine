"""Explicit session-key cloud transports; no SDK retries, proxies or fallback.

Profiles describe an API contract, not a claim of account/model availability.
Only the two fixed HTTPS destinations below can receive credentials. The normal
test suite injects HTTPS connections and never makes authenticated requests.
"""
from __future__ import annotations
from hashlib import sha256
import http.client
import math
import queue
import socket
import ssl
import threading
import time

from pydantic import ValidationError
from ..contracts import canonical, digest
from ..ports import MvpError
from ..proposal_contracts import ProposalGenerationResult, ProposalModelOutput, PROMPT_VERSION
from ..search_plan_contracts import (SearchPlanDraft, SearchPlanningCapability, SearchPlanningResult,
                                     PLANNER_PROMPT_VERSION)
from .cell_generation import strict_json_loads, ConfiguredCellGenerationAdapter, _SYSTEM as CELL_SYSTEM
from .search_planning import ConfiguredSearchPlanningAdapter, _SYSTEM as PLAN_SYSTEM

DESTINATIONS = {
    'openai': ('api.openai.com', '/v1/chat/completions', 'openai.chat-json.v1'),
    'deepseek': ('api.deepseek.com', '/chat/completions', 'deepseek.chat-json-nonthinking.v1'),
}
MAX_CLOUD_SECONDS = 30
MAX_CLOUD_RESPONSE_BYTES = 65536
_CLOUD_CALL_SLOT = threading.BoundedSemaphore(1)


class CloudJSONTransport:
    def __init__(self, provider, key, *, connection_factory=None, monotonic=time.monotonic):
        if provider not in DESTINATIONS or not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise MvpError('generation_configuration', 'Choose an approved provider and enter its session key.')
        self.provider, self._key = provider, key
        self.host, self.path, self.capability_profile = DESTINATIONS[provider]
        self._connection_factory = connection_factory
        self._monotonic = monotonic

    def request(self, body, timeout_seconds):
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= MAX_CLOUD_SECONDS):
            raise MvpError('generation_configuration', 'Cloud requests must have a bounded positive deadline.')
        if len(body) > 65536:
            raise MvpError('proposal_context_limit', 'The model input exceeds its bounded context budget.')
        # DNS/connect may block before a cancellable socket exists. A daemon
        # worker bounds caller runtime; its global lease is retained until the
        # actual transport exits, so timeouts cannot create unlimited orphans.
        if not _CLOUD_CALL_SLOT.acquire(blocking=False):
            raise MvpError('proposal_provider_failure', 'An earlier cloud request is still finishing. No new request was sent; retry explicitly later.')
        replies = queue.Queue(maxsize=1)
        def invoke():
            try:
                replies.put((True, self._request(body, timeout_seconds)))
            except BaseException as error:
                safe = error if isinstance(error, MvpError) else MvpError('proposal_provider_failure',
                    'Cloud transport failed. Usage may be unknown; no fallback or automatic retry was made.')
                replies.put((False, safe))
            finally:
                _CLOUD_CALL_SLOT.release()
        threading.Thread(target=invoke, daemon=True, name='bounded-session-cloud-call').start()
        try:
            ok, value = replies.get(timeout=timeout_seconds)
        except queue.Empty:
            raise MvpError('proposal_timeout', 'Cloud deadline expired. Usage or charges may be unknown. Its transport lease remains held until it exits; no retry was made.') from None
        if not ok: raise value
        return value

    def _request(self, body, timeout_seconds):
        deadline, connection, active = self._monotonic() + timeout_seconds, None, None
        expired = threading.Event()
        def interrupt():
            expired.set()
            sock = active or (connection.sock if connection else None)
            if sock:
                try: sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                sock.close()
        def remaining():
            value = deadline - self._monotonic()
            if value <= 0 or expired.is_set():
                raise MvpError('proposal_timeout', 'Cloud deadline expired. Provider usage and charges may be unknown; no automatic retry was made.')
            if active: active.settimeout(value)
            return value
        timer = threading.Timer(timeout_seconds, interrupt); timer.daemon = True
        try:
            if self._connection_factory:
                connection = self._connection_factory(self.host, 443, timeout=remaining())
            else:
                import certifi
                context = ssl.create_default_context(cafile=certifi.where())
                connection = http.client.HTTPSConnection(self.host, 443, timeout=remaining(), context=context)
            timer.start()
            connection.request('POST', self.path, body=body, headers={'Authorization': 'Bearer ' + self._key,
                'Content-Type': 'application/json', 'Accept': 'application/json', 'Accept-Encoding': 'identity'})
            active = connection.sock
            remaining()
            response = connection.getresponse()
            if response.status != 200:
                raise MvpError('proposal_provider_failure', 'The selected provider rejected the request. Check account/model access; no redirect, fallback or retry was attempted. Charges may be unknown.')
            length = response.getheader('Content-Length')
            if length is not None and (not length.isdigit() or int(length) > MAX_CLOUD_RESPONSE_BYTES):
                raise MvpError('proposal_invalid_output', 'The provider response exceeds the output bound.')
            if response.getheader('Content-Encoding', 'identity').lower() not in {'', 'identity'}:
                raise MvpError('proposal_invalid_output', 'Compressed provider output is unsupported.')
            chunks, count = [], 0
            while True:
                remaining()
                chunk = response.read1(min(4096, MAX_CLOUD_RESPONSE_BYTES + 1 - count))
                remaining()
                if not chunk: break
                count += len(chunk)
                if count > MAX_CLOUD_RESPONSE_BYTES:
                    raise MvpError('proposal_invalid_output', 'Provider output exceeds the bounded response size.')
                chunks.append(chunk)
            if length is not None and count != int(length):
                raise MvpError('proposal_invalid_output', 'Provider output was incomplete.')
            return b''.join(chunks)
        except MvpError:
            raise
        except (TimeoutError, socket.timeout):
            raise MvpError('proposal_timeout', 'Cloud deadline expired. Charges may be unknown; no automatic retry was made.') from None
        except (OSError, http.client.HTTPException, ValueError, TypeError):
            raise MvpError('proposal_provider_failure', 'Cloud transport failed. Usage may be unknown; no automatic retry or fallback was made.') from None
        finally:
            timer.cancel()
            if connection: connection.close()


class SessionCloudAdapter:
    enabled = True
    max_call_seconds = MAX_CLOUD_SECONDS

    def __init__(self, *, provider, model, model_revision, key, task, settings_revision, still_current,
                 transport=None):
        if task not in {'planning', 'proposals'} or not model or not model_revision:
            raise MvpError('generation_configuration', 'Select a versioned model and supported operation.')
        self.task, self.model, self.still_current = task, model, still_current
        self.transport = transport or CloudJSONTransport(provider, key)
        host, path, capability = DESTINATIONS[provider]
        self.provider = provider
        self.prompt_version = PLANNER_PROMPT_VERSION if task == 'planning' else PROMPT_VERSION
        self.system = PLAN_SYSTEM if task == 'planning' else CELL_SYSTEM
        schema = SearchPlanDraft if task == 'planning' else ProposalModelOutput
        self.profile = dict(adapter=capability, provider=provider, model=model, model_revision=model_revision,
            endpoint='https://' + host + path, settings_revision=settings_revision,
            prompt_version=self.prompt_version, system_prompt_sha256=sha256(self.system.encode()).hexdigest(),
            output_schema_sha256=digest(schema.model_json_schema()), max_input_bytes=24576 if task == 'planning' else 24000,
            max_response_bytes=24576 if task == 'planning' else 32768, max_output_tokens=4096 if task == 'planning' else 2048,
            timeout_seconds=MAX_CLOUD_SECONDS, max_calls=1 if task == 'planning' else 3,
            max_runtime_seconds=30 if task == 'planning' else 35, retries=0, paid_calls=True,
            cost_status='provider_metered_rate_unavailable', spend_cap_usd=None,
            revision_status='configured_not_weight_verified')

    def capability(self):
        return SearchPlanningCapability(enabled=True, model_profile=self.profile,
            reason='Session cloud provider configured, not live-tested. Each run requires explicit data/cost consent.')

    def _body(self, data):
        payload = dict(model=self.model, stream=False,
            response_format={'type': 'json_object'}, messages=[{'role': 'system', 'content': self.system},
                {'role': 'user', 'content': canonical(data)}])
        if self.provider == 'deepseek':
            payload['thinking'] = {'type': 'disabled'}
            payload['max_tokens'] = self.profile['max_output_tokens']
        else:
            payload['max_completion_tokens'] = self.profile['max_output_tokens']
        return canonical(payload).encode('utf-8')

    def _call(self, data, timeout_seconds):
        self.still_current()
        body = self._body(data)
        if len(body) > self.profile['max_input_bytes']:
            raise MvpError('proposal_context_limit', 'Instructions and input exceed the bounded context budget.')
        started = time.monotonic()
        payload = self.transport.request(body, min(timeout_seconds, MAX_CLOUD_SECONDS))
        self.still_current()
        if len(payload) > self.profile['max_response_bytes']:
            raise MvpError('proposal_invalid_output', 'The provider output exceeds this operation\'s response budget.')
        value = strict_json_loads(payload)
        if not isinstance(value, dict) or value.get('model') != self.model:
            raise MvpError('proposal_invalid_output', 'Provider output did not identify the configured model. Use an explicit supported model identifier; no fallback was used.')
        choices = value.get('choices')
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise MvpError('proposal_invalid_output', 'Provider must return one complete response.')
        choice, message = choices[0], choices[0].get('message')
        if (choice.get('finish_reason') != 'stop' or not isinstance(message, dict)
            or message.get('role') != 'assistant' or not isinstance(message.get('content'), str)
            or not message['content'].strip() or any(message.get(k) for k in ('refusal', 'tool_calls', 'function_call'))):
            raise MvpError('proposal_invalid_output', 'Provider returned empty, refused, truncated or action-bearing output.')
        content = message['content']
        strict_json_loads(content)
        return content, value.get('usage'), payload, time.monotonic() - started

    def generate(self, packet, *, timeout_seconds):
        if self.task != 'proposals':
            raise MvpError('generation_configuration', 'This adapter is scoped to a different operation.')
        text, usage, _, _ = self._call(packet.model_dump(mode='json'), timeout_seconds)
        return ProposalGenerationResult(output_text=text, usage=ConfiguredCellGenerationAdapter._usage(usage))

    def propose(self, original_question, *, timeout_seconds=MAX_CLOUD_SECONDS):
        if self.task != 'planning':
            raise MvpError('generation_configuration', 'This adapter is scoped to a different operation.')
        try:
            text, usage, payload, elapsed = self._call({'original_question': original_question}, timeout_seconds)
            draft = SearchPlanDraft.model_validate(strict_json_loads(text))
            if draft.original_question != original_question or draft.input_mode != 'natural_question' or draft.manual_strategy is not None:
                raise ValueError('question binding')
            concepts = [c.model_copy(update={'promoted_to_query': False, 'promotion_reason': '',
                'terms': [t.model_copy(update={'state': 'proposed', 'origin': 'model_proposed'}) for t in c.terms]}) for c in draft.concepts]
            ambiguities = [a.model_copy(update={'resolved': False, 'resolution': ''}) for a in draft.ambiguities]
            draft = draft.model_copy(update={'concepts': concepts, 'ambiguities': ambiguities})
            return SearchPlanningResult(draft=draft, question_sha256=sha256(original_question.encode()).hexdigest(),
                model_profile=dict(self.profile), response_sha256=sha256(payload).hexdigest(),
                elapsed_seconds=elapsed, usage=ConfiguredSearchPlanningAdapter._usage(usage))
        except (ValueError, ValidationError, TypeError):
            raise MvpError('search_planner_invalid_output', 'Provider output failed the typed search-plan contract; no plan was approved.') from None
