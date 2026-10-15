"""Loopback-only local reviewer HTTP surface with strict routes and CSRF checks."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading

from .assessments import list_assessments, save_assessment
from .contracts import MAX_ASSESSMENT_BYTES, canonical, read_bounded, read_json, require
from .receipts import public_packet


def create_server(packet, assessments_dir, port=0, reveal_methods=False):
    require(type(port) is int and 0 <= port <= 65535, "Port must be an integer from 0 to 65535")
    require(type(reveal_methods) is bool, "Method reveal must be boolean")
    list_assessments(packet, assessments_dir)
    token, lock = secrets.token_urlsafe(32), threading.Lock()
    assets = Path(__file__).with_name("static")

    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalReviewWorkbench/1"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass

        def send_error(self, code, message=None, explain=None):
            self._respond(code, {"error": "Invalid or unsupported local HTTP request"})

        def _respond(self, status, data, content_type="application/json; charset=utf-8"):
            if not isinstance(data, bytes):
                data = canonical(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

        def _local(self, mutation=False):
            authority = "127.0.0.1:" + str(self.server.server_port)
            require(self.headers.get_all("Host") == [authority], "Invalid local Host header")
            origin = self.headers.get_all("Origin")
            require(origin is None or origin == ["http://" + authority], "Cross-origin requests are forbidden")
            if mutation:
                require(origin == ["http://" + authority], "Save requires the exact local Origin")
                values = self.headers.get_all("X-Workbench-CSRF")
                require(values is not None and len(values) == 1 and secrets.compare_digest(values[0], token), "Invalid local CSRF token")

        def do_GET(self):
            try:
                self._local()
            except ValueError as error:
                return self._respond(403, {"error": str(error)})
            try:
                if self.path == "/":
                    from .page import render_page
                    return self._respond(200, render_page().encode("utf-8"), "text/html; charset=utf-8")
                if self.path in {"/assets/workbench.js", "/assets/workbench.css"}:
                    name = self.path.rsplit("/", 1)[1]
                    mime = "application/javascript; charset=utf-8" if name.endswith(".js") else "text/css; charset=utf-8"
                    return self._respond(200, read_bounded(assets / name, 2 * 1024 * 1024), mime)
                if self.path == "/api/session":
                    with lock:
                        records = list_assessments(packet, assessments_dir)
                    return self._respond(200, {"packet": public_packet(packet, reveal=reveal_methods), "assessments": records,
                                               "csrf_token": token, "reveal_methods": reveal_methods})
                return self._respond(404, {"error": "Unknown local route"})
            except (ValueError, KeyError, TypeError) as error:
                return self._respond(400, {"error": str(error)})
            except Exception:
                return self._respond(500, {"error": "Local workbench could not read its files"})

        def do_POST(self):
            try:
                self._local(mutation=True)
            except ValueError as error:
                return self._respond(403, {"error": str(error)})
            if self.path != "/api/assessments":
                return self._respond(404, {"error": "Unknown local route"})
            try:
                require(self.headers.get_all("Transfer-Encoding") is None, "Transfer encoding is not supported")
                lengths = self.headers.get_all("Content-Length")
                require(lengths is not None and len(lengths) == 1 and lengths[0].isascii() and lengths[0].isdigit(), "Expected one bounded Content-Length")
                length = int(lengths[0])
                require(0 < length <= MAX_ASSESSMENT_BYTES, "Assessment request exceeds its size bound")
                require(self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() == "application/json", "Expected application/json")
                data = self.rfile.read(length)
                require(len(data) == length, "Incomplete JSON request")
                draft = read_json(data)
                with lock:
                    record = save_assessment(packet, assessments_dir, draft, display_mode="revealed" if reveal_methods else "blinded")
                return self._respond(201, {"assessment": record})
            except (ValueError, KeyError, TypeError, OverflowError) as error:
                return self._respond(400, {"error": str(error)})
            except Exception:
                return self._respond(500, {"error": "Local workbench could not save the assessment"})

        def do_OPTIONS(self):
            self._respond(405, {"error": "Unsupported local method"})

        do_PUT = do_OPTIONS
        do_DELETE = do_OPTIONS
        do_PATCH = do_OPTIONS
        do_HEAD = do_OPTIONS
        do_TRACE = do_OPTIONS
        do_CONNECT = do_OPTIONS

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.csrf_token = token
    return server
