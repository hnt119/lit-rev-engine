"""Exact owner-approved code license and required source-distribution notices.

This stdlib-only helper performs no installation, network, model or data calls.
"""
import hashlib
from pathlib import Path

MIT_LICENSE_TEXT = 'MIT License\n\nCopyright (c) 2026 Yixuan Huang\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the "Software"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.\n'
MIT_LICENSE_SHA256 = hashlib.sha256(MIT_LICENSE_TEXT.encode("utf-8")).hexdigest()
THIRD_PARTY_BOUNDARY = "Third-party material is not relicensed under MIT."


def validate_distribution_license(root):
    root = Path(root).resolve()
    license_path = root / "LICENSE"
    notice = root / "THIRD_PARTY_NOTICES.md"
    terms = root / "docs" / "local_preview_distribution_terms.md"
    if not terms.is_file():
        terms = root / "DISTRIBUTION_TERMS.md"
    for path in (license_path, notice, terms):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Required MIT license and distribution notices must be ordinary retained files")
    if license_path.read_bytes() != MIT_LICENSE_TEXT.encode("utf-8"):
        raise ValueError("LICENSE must contain the exact approved standard MIT text and owner copyright")
    if THIRD_PARTY_BOUNDARY not in notice.read_text(encoding="utf-8"):
        raise ValueError("Required third-party license boundaries are absent from THIRD_PARTY_NOTICES.md")
    text = terms.read_text(encoding="utf-8")
    if "SPDX-License-Identifier: MIT" not in text or THIRD_PARTY_BOUNDARY not in text:
        raise ValueError("Distribution terms must retain MIT identification and third-party boundaries")
    return {"spdx_license": "MIT", "license_sha256": MIT_LICENSE_SHA256,
            "required_notices": ["LICENSE", "THIRD_PARTY_NOTICES.md", "DISTRIBUTION_TERMS.md"]}
