"""Test-only private Windows directories, without changing pre-existing owners.

Elevated hosted runners can give ordinary tempfile/pytest directories an
Administrators-group owner. Research code correctly refuses that owner. Create
new dedicated fixture children with the real current-SID descriptor instead.
"""
import os
import pytest


@pytest.fixture
def tmp_path(tmp_path):
    if os.name != 'nt': return tmp_path
    from src.platform_support import private_directory
    return private_directory(tmp_path.resolve() / 'current-SID-owned-fixture')
