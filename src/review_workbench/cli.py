"""Standalone local workbench commands; no model, credential or ledger access."""

import argparse
from io import BytesIO
import os
from pathlib import Path
import tarfile

from .assessments import list_assessments, save_assessment
from .contracts import (MAX_ASSESSMENT_BYTES, MAX_RECEIPT_BYTES, absolute_path, canonical, directory_fd,
                        read_bounded, read_json, require, sha256, write_at_new, write_new)
from .evaluation import summarize
from .receipts import load_packet

ROOT = Path(__file__).resolve().parents[2]
DEMO_DIRECTORY = ROOT / "tests/fixtures/qwen_components_confirmation_run_v1"
DEMO_MANIFEST_SHA256 = "7f26a08f0c5b1c4bb837636c0c906e7f61ebaa856ab98124394453e6a65da8d8"
DEMO_RECEIPT_SHA256 = "3ba4da317d497cc021a90e9dcc9f88b3667bbdba85e7f94b633f7427dc7a9c80"


def demo(output):
    requested = Path(output)
    require(requested.is_absolute() and ".." not in requested.parts, "Demo output must be an explicit absolute new directory")
    manifest_bytes = read_bounded(DEMO_DIRECTORY / "manifest.json", MAX_ASSESSMENT_BYTES)
    require(sha256(manifest_bytes) == DEMO_MANIFEST_SHA256, "Committed demo manifest differs from its pinned bytes")
    manifest = read_json(manifest_bytes)
    archive_meta = manifest["archive"]
    archive_bytes = read_bounded(DEMO_DIRECTORY / "artifacts.tar.xz", 4 * 1024 * 1024)
    require(len(archive_bytes) == archive_meta["size_bytes"] and sha256(archive_bytes) == archive_meta["sha256"],
            "Committed demo archive checksum mismatch")
    expected = manifest["archive_members"]
    receipt, seen, total = None, set(), 0
    with tarfile.open(fileobj=BytesIO(archive_bytes), mode="r:xz") as archive:
        for member in archive:
            require(member.isfile() and member.name in expected and member.name not in seen,
                    "Demo archive contains an unexpected, duplicate or non-regular member")
            seen.add(member.name)
            pin = expected[member.name]
            require(member.size == pin["size_bytes"] and member.size <= MAX_RECEIPT_BYTES, "Demo member size differs")
            total += member.size
            require(total <= archive_meta["uncompressed_tar_bytes"], "Demo archive exceeds its retained bound")
            stream = archive.extractfile(member)
            data = stream.read(member.size + 1)
            require(len(data) == member.size and sha256(data) == pin["sha256"], "Demo member checksum differs")
            if member.name == "validation.receipt.json":
                receipt = data
    require(seen == set(expected) and len(seen) == archive_meta["member_count"]
            and receipt is not None and sha256(receipt) == DEMO_RECEIPT_SHA256, "Demo archive member roster differs")
    output_path = absolute_path(requested)
    with directory_fd(output_path.parent, create=True) as parent_fd:
        try:
            os.mkdir(output_path.name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            raise ValueError("Demo output already exists; choose a new directory") from None
    with directory_fd(output_path) as output_fd:
        write_at_new(output_fd, "validation.receipt.json", receipt)
    return {"receipt": str(output_path / "validation.receipt.json"), "receipt_sha256": DEMO_RECEIPT_SHA256,
            "assessment_records_created": 0, "use": "Exposed public licensed regression material only; no human decisions or new inference."}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    demonstration = commands.add_parser("demo", help="Copy only the trusted original receipt into an absent directory")
    demonstration.add_argument("--output", required=True)
    for name in ("serve", "assess", "evaluate"):
        command = commands.add_parser(name)
        command.add_argument("--receipt", required=True)
        command.add_argument("--receipt-sha256", required=True, help="Externally trusted SHA256 of the whole receipt file")
        command.add_argument("--assessments", required=True, help="Dedicated local assessment directory")
        if name == "serve":
            command.add_argument("--port", type=int, default=0)
            command.add_argument("--show-methods", action="store_true", help="Reveal methods/scores/reasons and record that display mode")
        elif name == "assess":
            command.add_argument("--input", required=True, help="Exact JSON assessment draft")
            command.add_argument("--show-methods", action="store_true")
        else:
            command.add_argument("--output", required=True, help="New immutable JSON report path")
    return result


def main(argv=None):
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "demo":
            print(canonical(demo(arguments.output)))
            return 0
        packet = load_packet(arguments.receipt, arguments.receipt_sha256)
        if arguments.command == "assess":
            draft = read_json(read_bounded(arguments.input, MAX_ASSESSMENT_BYTES))
            record = save_assessment(packet, arguments.assessments, draft,
                                     display_mode="revealed" if arguments.show_methods else "blinded")
            print(canonical({"assessment": record}))
        elif arguments.command == "evaluate":
            report = summarize(packet, list_assessments(packet, arguments.assessments))
            write_new(arguments.output, report)
            print(canonical({"output": str(absolute_path(arguments.output)), "report_sha256": report["report_sha256"],
                             "current_assessment_records": report["current_assessment_records"], "independent_verification": "NOT_RUN"}))
        else:
            from .server import create_server
            server = create_server(packet, arguments.assessments, arguments.port, arguments.show_methods)
            print("Local reviewer: http://127.0.0.1:" + str(server.server_port) + "/", flush=True)
            print("Single human judgments; source answerability not assessed; independent verification NOT_RUN.", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        return 0
    except (ValueError, OSError, KeyError, TypeError, tarfile.TarError) as error:
        print(canonical({"error": str(error)}))
        return 2
