#!/usr/bin/env python3
"""Inspect validated launcher configuration without model/provider calls.

Use local_preview.py check-config so settings are validated and the private
application Python environment is selected. This script never starts a server,
loads weights, downloads files, fits a map or creates a research workspace.
"""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def inspect_configuration(environ=None):
    env = os.environ if environ is None else environ
    result = {'status': 'CONFIGURATION_INSPECTED', 'model_calls': 0, 'provider_calls': 0,
              'downloads': 0, 'capabilities': {}}
    capabilities = result['capabilities']
    capabilities['live_pubmed'] = {'enabled': bool(env.get('NCBI_EMAIL')), 'connectivity': 'NOT_RUN',
        'note': 'Only explicit live discovery/diagnostic actions contact NCBI; configuration is not evidence of search availability or quality.'}
    try:
        from src.mvp.adapters.cell_generation import ConfiguredCellGenerationAdapter
        from src.mvp.adapters.search_planning import ConfiguredSearchPlanningAdapter
        for name, adapter in (('search_planner', ConfiguredSearchPlanningAdapter),
                              ('cell_proposals', ConfiguredCellGenerationAdapter)):
            configured = adapter.from_environment(env)
            capabilities[name] = {'enabled': configured.enabled, 'adapter_configured': configured.enabled,
                'server_connectivity': 'NOT_RUN', 'real_inference': 'NOT_RUN',
                'note': 'Requires a separately operated loopback model server. No call, weight verification or provider fallback was performed.'}
        maps = env.get('MVP_MAP_ENABLED') == '1'
        if maps:
            from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder
            embedder = LocalPaperEmbedder(enabled=True, cache_dir=env.get('HF_HUB_CACHE'))
            ready, reason = embedder.readiness()
            capabilities['new_maps'] = {'enabled': True, 'setup_ready': ready, 'reason': reason,
                'weights_loaded': False, 'new_map_computed': False, 'real_model_check': 'NOT_RUN'}
        else:
            capabilities['new_maps'] = {'enabled': False, 'setup_ready': False,
                'reason': 'Explicitly install optional pinned mapping dependencies and weights, then enable maps in your private settings.',
                'weights_loaded': False, 'new_map_computed': False, 'real_model_check': 'NOT_RUN'}
    except ImportError:
        result.update(status='SETUP_REQUIRED', error='Run setup using the extracted application; the locked base runtime is incomplete.')
        return result, 2
    except Exception:
        # Existing adapters provide fixed, sanitized configuration errors; never
        # print arbitrary exception text or private environment values here.
        result.update(status='CONFIGURATION_REJECTED', error='An existing adapter rejected its configuration; check the private settings guide.')
        return result, 2
    return result, 2 if capabilities['new_maps']['enabled'] and not capabilities['new_maps']['setup_ready'] else 0


def main():
    result, code = inspect_configuration()
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
