"""Shared selection policy, independent of any UI or retrieval/model budget.

The legacy synchronous preparation path stays bounded at ten. Larger selections
must use the durable preparation worker, once its capability is available.
"""

MAX_PREPARED_SOURCES = 30
MAX_SYNCHRONOUS_PREPARED_SOURCES = 10
MAX_BOARD_PAPERS = 30
MAX_BOARD_FIELDS = 6
MAX_BOARD_CELLS = MAX_BOARD_PAPERS * MAX_BOARD_FIELDS
DEFAULT_PASSAGES = 5
MAX_PASSAGES = 30
MAX_DISCOVERY_RESULTS = 50
DEFAULT_DISCOVERY_RESULTS = 30
MAX_IMPORT_ROWS = 500
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_RESOLUTION_ROWS = 3
MAX_COLLECTION_MAP_PAPERS = 50


def public_limits():
    return {
        "default_results": DEFAULT_DISCOVERY_RESULTS,
        "max_results": MAX_DISCOVERY_RESULTS,
        "max_sources": MAX_PREPARED_SOURCES,  # Existing clients' selection key.
        "max_prepared_sources": MAX_PREPARED_SOURCES,
        "max_synchronous_prepared_sources": MAX_SYNCHRONOUS_PREPARED_SOURCES,
        "default_passages": DEFAULT_PASSAGES,
        "max_passages": MAX_PASSAGES,
        "max_board_papers": MAX_BOARD_PAPERS,
        "max_board_fields": MAX_BOARD_FIELDS,
        "max_board_cells": MAX_BOARD_CELLS,
        "max_proposal_cells": 9,
        "max_proposal_calls": 3,
        "max_import_rows": MAX_IMPORT_ROWS,
        "max_import_bytes": MAX_IMPORT_BYTES,
        "max_import_resolution_rows": MAX_IMPORT_RESOLUTION_ROWS,
        "max_map_papers": MAX_COLLECTION_MAP_PAPERS,
    }
