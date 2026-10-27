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
NATIVE_DOWNLOAD = "https://github.com/hnt119/lit-rev-engine/releases/download/" + NATIVE + "/lit-rev-engine-0.3.0-desktop-beta.2-macos-arm64.dmg"
DOCS = ROOT / "docs/releases" / NATIVE
PUBLISHED_DOCS = {
    "INSTALL_MAC.md": "bd3eb35baa29dd287d26cc6696f5a28b4bec0cda1c49477a6981f7df87e2ba70",
    "VALIDATION.md": "ebca08ea60c7d5a9a6143c94737aeb48105dacf4270c602944a9e4c774e821cc",
}


def test_first_actions_separate_published_native_from_source_and_windows():
    text = (ROOT / "README.md").read_text()
    first = text.split("## Start locally", 1)[0]
    assert first.startswith("# Literature Review Engine\n\nAn open-source, local-first workspace for comparing papers and checking the source behind each research note.")
    assert "[Download for macOS](" + NATIVE_DOWNLOAD + ")" in first
    secondary = next(line for line in first.splitlines() if line.startswith("[Getting started]"))
    for label, target in [
        ("Getting started", "docs/releases/" + NATIVE + "/INSTALL_MAC.md"),
        ("User guide", "docs/user_manual.md"),
        ("Demo", "https://hnt119.github.io/projects/literature-review-engine/#saved-evidence"),
        ("Release notes", NATIVE_RELEASE),
        ("Architecture", "docs/application_architecture.md"),
    ]:
        assert "[" + label + "](" + target + ")" in secondary
    assert "| Windows · x64 | Windows installer not yet published |" in first
    assert "UNNOTARIZED" in first and "ad-hoc signed" in first and "no Apple Developer ID signature" in first
    assert "169.6 MB" in first and "27 October 2026" in first
    assert "[Download for Windows](" not in text and "/releases/latest" not in text
    assert "matching library capsule is not publicly offered" in text
    assert not re.search(r"!\[|<\s*(?:img|picture|video)\b", text, re.I)


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
    assert {
        "literature-review-engine", "start-locally", "review-an-entry", "your-first-comparison",
        "choose-retrieval-in-the-same-app", "how-rag-fits-into-the-workflow", "under-the-hood",
        "help-privacy-and-status", "requirements-and-installation", "update-main-and-contribute",
    } <= anchors(before)
    assert 'I["Search / import<br/>Retain sources"] --> R["Retrieve excerpts<br/>Core / Qwen / MedCPT"]' in before
    assert 'R --> H["Human comparison<br/>Source-linked exports"]' in before


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
