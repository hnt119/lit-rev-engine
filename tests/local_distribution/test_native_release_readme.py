"""Documentation-only guards for native and source release entry points."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

from scripts.release_links import ROOT, block


NATIVE = "v0.3.0-desktop-beta.2"
NATIVE_RELEASE = "https://github.com/hnt119/lit-rev-engine/releases/tag/" + NATIVE
DOCS = ROOT / "docs/releases" / NATIVE
PUBLISHED_DOCS = {
    "INSTALL_MAC.md": "bd3eb35baa29dd287d26cc6696f5a28b4bec0cda1c49477a6981f7df87e2ba70",
    "VALIDATION.md": "ebca08ea60c7d5a9a6143c94737aeb48105dacf4270c602944a9e4c774e821cc",
}


def test_first_actions_separate_published_native_from_source_and_windows():
    text = (ROOT / "README.md").read_text()
    first = text.split("## Start locally", 1)[0]
    assert first.startswith("# Literature Review Engine\n\n*An open-source, local-first research workspace for discovering papers, comparing evidence, and reviewing source-linked findings.*")
    assert "[Download for macOS](" + NATIVE_RELEASE + ")" in first
    assert "[Installation guide](docs/releases/" + NATIVE + "/INSTALL_MAC.md)" in first
    assert "[Try Interactive Demo](https://hnt119.github.io/projects/literature-review-engine/#saved-evidence)" in first
    assert "**Windows installer: unavailable.**" in first
    assert "UNNOTARIZED" in first and "no Apple Developer ID signature" in first
    assert "169,622,385 bytes" in first and "27 October 2026" in first
    assert "[Download for Windows](" not in text and "/releases/latest" not in text
    assert "matching library capsule is not publicly offered" in text


def test_readable_native_guides_are_exact_copies_of_verified_published_assets():
    for name, expected in PUBLISHED_DOCS.items():
        data = (DOCS / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected
        assert b"0.3.0-desktop-beta.2" in data
        assert b"30c08636b310f88848bf49d40eed9b6eed8b5bcb84e90fa09ef6a1e84978c0d8" in data
    assert b"https://support.apple.com/en-us/102445" in (DOCS / "INSTALL_MAC.md").read_bytes()


def test_source_generator_is_still_source_beta4_and_preserves_native_actions(tmp_path):
    value = json.loads((ROOT / "config/public_release.json").read_text())
    assert value["tag"] == "v0.3.0-beta.4"
    before = (ROOT / "README.md").read_text()
    assert block(value) in before
    (tmp_path / "scripts").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "scripts/release_links.py").write_bytes((ROOT / "scripts/release_links.py").read_bytes())
    (tmp_path / "config/public_release.json").write_text(json.dumps(value))
    (tmp_path / "README.md").write_text(before)
    subprocess.run([sys.executable, str(tmp_path / "scripts/release_links.py"), "--write-readme"], check=True, capture_output=True)
    assert (tmp_path / "README.md").read_text() == before
    assert '<a id="requirements-and-installation"></a>' in before
    assert '<a id="update-main-and-contribute"></a>' in before
    assert 'I["Search / import<br/>Retain sources"] --> R["Retrieve excerpts<br/>Core / Qwen / MedCPT"]' in before


def anchors(text):
    result = set(re.findall(r'<a\s+id="([^"]+)"', text))
    for heading in re.findall(r"^#{1,6}\s+(.+)$", text, re.M):
        heading = re.sub(r"<[^>]+>", "", heading).lower()
        result.add(re.sub(r"[^\w\- ]", "", heading).replace(" ", "-"))
    return result


def test_affected_local_document_links_and_fragments_resolve():
    paths = [ROOT / "README.md", ROOT / "docs/README.md", ROOT / "docs/application_architecture.md", *(DOCS / name for name in PUBLISHED_DOCS)]
    for path in paths:
        text = path.read_text()
        for href in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            url = urlsplit(href)
            if url.scheme or url.netloc:
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            assert target.exists(), (path.name, href)
            if url.fragment and target.suffix == ".md":
                assert unquote(url.fragment) in anchors(target.read_text()), (path.name, href)
