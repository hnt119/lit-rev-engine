"""v0.2 software-only preview: fixed public source fixtures, never live PubMed.

Run with explicit isolated data directory and loopback API/web ports. The saved
example fixture validates rights, hashes and exact identifiers before use.
"""
import os
import sys
from pathlib import Path

root, data, api_port, web_port = sys.argv[1:]
sys.path.insert(0, root)
for key in tuple(os.environ):
    if key.startswith(('MVP_', 'NCBI_', 'OPENAI_', 'DEEPSEEK_')):
        del os.environ[key]
os.environ.update(MVP_MAP_ENABLED='0', MVP_SEARCH_PLANNER_ENABLED='0', MVP_PROPOSALS_ENABLED='0')
from src.mvp.adapters.saved_examples import SavedExampleProvider
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.adapters.search_diagnostics import PubMedSearchDiagnostics
from src.mvp.adapters.transport import BoundedTransport
from src.mvp.contracts import SearchPreview, SearchRequest
from src.mvp.service import MVPService
from src.web_api.app import create_app


def denied(*args, **kwargs):
    raise AssertionError('External transport forbidden in offline research preview')


BoundedTransport.request = denied
saved = SavedExampleProvider()
fixtures = saved.search(SearchRequest(request_id='fixture-inventory', query='fixed fixture inventory', max_results=30)).papers
WARNING = 'SIMULATED SEARCH: fixed public fixture papers. This query was not executed against PubMed. No relevance or scientific validation is claimed.'


class Discovery:
    def search(self, request):
        available = fixtures[:2] if request.query == 'SYNTHETIC INITIAL' else fixtures[2:5]
        papers = available[:request.max_results]
        return SearchPreview(query=request.query, date_from=request.date_from, date_to=request.date_to,
            sort=request.sort, mode='live', provider='SIMULATED offline public-fixture search', papers=papers,
            total_reported=len(available), fetched_count=len(papers), truncated=len(papers)<len(available),
            ordered_identifiers=[p.pmid for p in papers], warnings=[WARNING])


class Diagnostics:
    def request(self, endpoint, params):
        assert endpoint == 'pubmed_search'
        return b'<eSearchResult><Count>3</Count><RetMax>0</RetMax><RetStart>0</RetStart><IdList/><QueryTranslation>SIMULATED diagnostic; query not sent to PubMed</QueryTranslation></eSearchResult>'


storage = SQLiteWorkspaceStorage(Path(data).resolve() / 'workspaces.sqlite3')
app = create_app(Path(data).resolve(), allowed_host=f'127.0.0.1:{api_port}', allowed_origin=f'http://127.0.0.1:{web_port}',
    services={'live': MVPService(storage, Discovery(), saved), 'saved_example': MVPService(storage, saved, saved)},
    search_diagnostics=PubMedSearchDiagnostics(email='qa@example.org', transport=Diagnostics()))
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=int(api_port), access_log=False, log_level='warning')
