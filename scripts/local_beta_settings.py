"""Strict private opt-in settings for the source-only local beta.

Only the named existing adapters can be enabled. This module uses the standard
library, makes no calls, imports no model stack and never prints setting values.
"""
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

from scripts.run_web import LocalLaunchError

SCHEMA = 'litrev.local-beta.settings.v1'
MAX_SETTINGS_BYTES = 16384
FEATURES = ('live', 'maps', 'search_planner', 'cell_proposals')
KEYS = {
    'live': {'enabled', 'email', 'api_key'},
    'maps': {'enabled', 'cache_dir'},
    'search_planner': {'enabled', 'url', 'model', 'model_revision'},
    'cell_proposals': {'enabled', 'url', 'model', 'model_revision'},
}


def _failure(message):
    raise LocalLaunchError('Local beta settings: ' + message)


def _text(value, label, maximum):
    if not isinstance(value, str) or len(value) > maximum or any(ord(char) < 32 or ord(char) == 127 for char in value):
        _failure(label + ' must be bounded plain text without control characters.')
    try:
        value.encode('utf-8')
    except UnicodeError:
        _failure(label + ' must contain valid Unicode text.')
    return value


def _endpoint(value):
    try:
        target = urlsplit(value)
        valid = (target.scheme == 'http' and target.hostname in {'127.0.0.1', '::1'}
            and target.username is None and target.password is None
            and not target.query and not target.fragment
            and target.path == '/v1/chat/completions'
            and target.port is not None and 1 <= target.port <= 65535)
    except ValueError:
        valid = False
    if not valid:
        _failure('use the existing literal HTTP loopback /v1/chat/completions adapter with an explicit port. Remote endpoints, credentials and fallback are unsupported.')


def validate_settings(value, app_root):
    if not isinstance(value, dict) or value.get('schema') != SCHEMA or set(value) - {'schema', *FEATURES}:
        _failure('use the supported schema and named feature sections only; arbitrary environment variables and resource-budget overrides are unsupported.')
    result = {'schema': SCHEMA}
    for feature in FEATURES:
        section = value.get(feature, {})
        if not isinstance(section, dict) or set(section) - KEYS[feature] or type(section.get('enabled', False)) is not bool:
            _failure('feature sections require an explicit boolean enabled flag and supported settings only.')
        current = {'enabled': section.get('enabled', False)}
        if feature == 'live':
            email = _text(section.get('email', ''), 'contact email', 320)
            key = _text(section.get('api_key', ''), 'optional NCBI API key', 128)
            if (email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)) or (current['enabled'] and not email):
                _failure('enabled live PubMed requires a valid privately supplied contact email.')
            if key and not re.fullmatch(r'[A-Za-z0-9_-]{10,128}', key):
                _failure('the optional NCBI API key has an invalid format.')
            current.update(email=email, api_key=key)
        elif feature == 'maps':
            cache = _text(section.get('cache_dir', ''), 'optional model cache directory', 4096)
            if cache:
                path = Path(cache).expanduser()
                if not path.is_absolute() or '..' in path.parts or path.resolve().is_relative_to(Path(app_root).resolve()):
                    _failure('keep the optional model cache at an absolute external path, separate from replaceable application files.')
                cache = str(path)
            current['cache_dir'] = cache
        else:
            url = _text(section.get('url', ''), 'local generation URL', 2048)
            model = _text(section.get('model', ''), 'configured model name', 200)
            revision = _text(section.get('model_revision', ''), 'configured model revision', 200)
            if url:
                _endpoint(url)
            if current['enabled'] and (not url or not model.strip() or not revision.strip()):
                _failure('enabled local planning/proposals require one explicit loopback URL, model name and revision.')
            current.update(url=url, model=model, model_revision=revision)
        result[feature] = current
    return result


def load_settings(path, app_root):
    if path is None:
        return validate_settings({'schema': SCHEMA}, app_root)
    path = Path(path).expanduser()
    if not path.is_absolute() or '..' in path.parts or path.resolve().is_relative_to(Path(app_root).resolve()):
        _failure('use an absolute private settings path outside the extracted application.')
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        _failure('settings must use an ordinary file without symlink paths.')
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_SETTINGS_BYTES:
                _failure('settings must be an ordinary file owned by you, mode 0600 and at most 16 KiB. Copy the sample outside the app and run chmod 600 on that private copy.')
            with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                raw = stream.read(MAX_SETTINGS_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(raw) > MAX_SETTINGS_BYTES:
            _failure('the settings file exceeds 16 KiB.')
        def pairs(items):
            output = {}
            for key, item in items:
                if key in output:
                    raise ValueError('duplicate settings key')
                output[key] = item
            return output
        def reject_constant(_value):
            raise ValueError('non-JSON constant')
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)
    except LocalLaunchError:
        raise
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        _failure('could not read valid private JSON settings. No setting values were printed or forwarded.')
    return validate_settings(value, app_root)


def feature_environment(settings):
    """Return only explicitly validated settings, never arbitrary process input."""
    result = {'MVP_MAP_ENABLED': '0', 'MVP_SEARCH_PLANNER_ENABLED': '0', 'MVP_PROPOSALS_ENABLED': '0',
              'MVP_SEARCH_PLANNER_SPEND_CAP_USD': '0', 'MVP_PROPOSALS_SPEND_CAP_USD': '0',
              'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1'}
    if settings['live']['enabled']:
        result['NCBI_EMAIL'] = settings['live']['email']
        if settings['live']['api_key']:
            result['NCBI_API_KEY'] = settings['live']['api_key']
    if settings['maps']['enabled']:
        result['MVP_MAP_ENABLED'] = '1'
        if settings['maps']['cache_dir']:
            result['HF_HUB_CACHE'] = settings['maps']['cache_dir']
    for feature, prefix in (('search_planner', 'MVP_SEARCH_PLANNER'), ('cell_proposals', 'MVP_PROPOSALS')):
        current = settings[feature]
        if current['enabled']:
            result[prefix + '_ENABLED'] = '1'
            for name in ('url', 'model', 'model_revision'):
                result[prefix + '_' + name.upper()] = current[name]
    return result
