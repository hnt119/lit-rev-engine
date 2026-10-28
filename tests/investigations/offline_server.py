"""Disposable integration server; synthetic follow-up results, public saved sources."""
import os
import sys
from pathlib import Path

root, data, api_port, web_port = sys.argv[1:]
data = Path(data).resolve()
sys.path.insert(0, root)
for key in tuple(os.environ):
    if key.startswith(('MVP_', 'NCBI_', 'OPENAI_', 'DEEPSEEK_')):
        del os.environ[key]
os.environ.update(MVP_MAP_ENABLED='0', MVP_SEARCH_PLANNER_ENABLED='0', MVP_PROPOSALS_ENABLED='0')
from src.mvp.adapters.saved_examples import SavedExampleProvider
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.adapters.search_diagnostics import PubMedSearchDiagnostics
from src.mvp.adapters.transport import BoundedTransport
from src.mvp.contracts import Paper, SearchPreview
from src.mvp.service import MVPService
from src.web_api.app import create_app

def denied(*args, **kwargs):
    raise AssertionError('External transport forbidden in browser software QA')
BoundedTransport.request = denied
saved = SavedExampleProvider()

class Discovery:
    def search(self, request):
        if request.query == 'SYNTHETIC INITIAL':
            result = saved.search(request)
            return result.model_copy(update=dict(query=request.query, date_from=request.date_from,
                date_to=request.date_to, sort=request.sort, provider='synthetic-browser-fixture', mode='live'))
        papers = [Paper(pmid=str(90000000+i), title=f'SYNTHETIC candidate {i} — software QA only',
            abstract='Synthetic metadata. No scientific judgment.', year=2026) for i in range(1, 4)]
        return SearchPreview(query=request.query, date_from=request.date_from, date_to=request.date_to,
            sort=request.sort, mode='live', provider='synthetic-browser-fixture', papers=papers[:request.max_results],
            total_reported=3, fetched_count=min(3, request.max_results), truncated=request.max_results<3,
            ordered_identifiers=[p.pmid for p in papers[:request.max_results]])

class Diagnostics:
    def request(self, endpoint, params):
        assert endpoint == 'pubmed_search'
        return b'<eSearchResult><Count>3</Count><RetMax>1</RetMax><RetStart>0</RetStart><IdList><Id>90000001</Id></IdList><QueryTranslation>SYNTHETIC fixture translation</QueryTranslation></eSearchResult>'

storage = SQLiteWorkspaceStorage(Path(data) / 'workspaces.sqlite3')
app = create_app(Path(data), allowed_host=f'127.0.0.1:{api_port}', allowed_origin=f'http://127.0.0.1:{web_port}',
    services={'live': MVPService(storage, Discovery(), saved), 'saved_example': MVPService(storage, saved, saved)},
    search_diagnostics=PubMedSearchDiagnostics(email='qa@example.org', transport=Diagnostics()))
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=int(api_port), access_log=False, log_level='warning')
