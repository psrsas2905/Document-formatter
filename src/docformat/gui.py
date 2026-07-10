"""Local web GUI for non-technical writers.

Serves a single-page app on 127.0.0.1 (stdlib http.server — no new runtime
dependencies, no CDN assets, nothing leaves the machine). The writer drops in
a raw draft, optionally their organization's brand template, and gets back the
formatted .docx, tagged PDF and QA report as downloads.
"""

from __future__ import annotations

import email.parser
import email.policy
import json
import logging
import re
import shutil
import sys
import tempfile
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from . import apply as _apply
from . import classify as _classify
from . import convert as _convert
from . import classify_ai as _classify_ai
from . import elements as _elements
from . import export as _export
from . import ingest as _ingest
from . import qa as _qa
from .errors import friendly as _friendly
from .errors import known_errors as _known_errors
from .template import apply_field_values, load_profile

_ASSET = Path(__file__).parent / "assets" / "gui.html"

_CONTENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".md": "text/markdown; charset=utf-8",
}


def _ai_available() -> bool:
    """True if a local Ollama model is actually reachable (offline probe).
    Never raises — the AI path is optional and degrades to heuristics."""
    try:
        return _classify_ai._pick_model() is not None
    except Exception:  # noqa: BLE001
        return False


def default_profile_path() -> Path | None:
    """Find the example profile: working dir first, then a PyInstaller bundle."""
    candidates = [Path("config/template_profile.example.yaml")]
    if getattr(sys, "_MEIPASS", None):  # PyInstaller onefile extraction dir
        candidates.append(Path(sys._MEIPASS) / "config" / "template_profile.example.yaml")
    for c in candidates:
        if c.exists():
            return c
    return None


MAX_UPLOAD_BYTES = 100 * 2**20  # cap request bodies at 100 MB
MAX_SESSIONS = 20  # oldest session dirs are evicted (and deleted) beyond this

_log = logging.getLogger("docformat.gui")


class _Handler(BaseHTTPRequestHandler):
    server_version = "docformat"
    protocol_version = "HTTP/1.1"  # keep-alive; we always send Content-Length
    timeout = 60  # a stalled client can't pin a handler thread forever
    profile_path: Path  # set by serve()
    sessions: dict[str, Path]  # sid -> output dir
    work_dir: Path

    # -- request guards ----------------------------------------------------
    #
    # The server binds 127.0.0.1, but browsers will happily POST here from
    # any web page (multipart is a CORS "simple" request) and DNS rebinding
    # defeats same-origin checks — so validate Host on everything and Origin
    # on state-changing requests.

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1")

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True  # non-browser clients (curl, tests) send no Origin
        return origin.startswith(("http://127.0.0.1:", "http://localhost:")) or origin in (
            "http://127.0.0.1",
            "http://localhost",
        )

    # -- routing ---------------------------------------------------------

    def do_GET(self):
        if not self._host_ok():
            self._send(403, "text/plain", b"forbidden host")
            return
        if self.path in ("/", "/index.html"):
            page = _ASSET.read_bytes().replace(b"__VERSION__", __version__.encode())
            self._send(200, "text/html; charset=utf-8", page)
            return
        if self.path == "/meta":
            self._send(200, "application/json", json.dumps(self._meta()).encode())
            return
        if self.path == "/favicon.ico":
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
                '<rect width="16" height="16" rx="3" fill="#1f4e79"/>'
                '<text x="8" y="12" font-size="10" font-weight="bold" fill="#fff" '
                'text-anchor="middle" font-family="sans-serif">D</text></svg>'
            )
            self._send(200, "image/svg+xml", svg.encode())
            return
        m = re.fullmatch(r"/files/([0-9a-f]{32})/([\w][\w. -]*)", self.path)
        if m and m.group(1) in self.sessions:
            file = self.sessions[m.group(1)] / m.group(2)
            if file.is_file():
                ctype = _CONTENT_TYPES.get(file.suffix, "application/octet-stream")
                self._send(200, ctype, file.read_bytes(), download=file.name)
                return
        self._send(404, "text/plain", b"not found")

    def do_POST(self):
        if not self._host_ok() or not self._origin_ok():
            self._send(403, "application/json", b'{"error": "forbidden origin"}')
            return
        if self.path != "/format":
            self._send(404, "text/plain", b"not found")
            return
        if int(self.headers.get("Content-Length", "0")) > MAX_UPLOAD_BYTES:
            self._send(
                413,
                "application/json",
                json.dumps({"error": "Upload too large (limit 100 MB)."}).encode(),
            )
            return
        try:
            fields = self._read_multipart()
            result = self._run_pipeline(fields)
            self._send(200, "application/json", json.dumps(result).encode())
        except _known_errors() as exc:  # expected failures: message is safe to show
            _log.warning("format request failed: %s", exc)
            self._send(400, "application/json", json.dumps({"error": _friendly(exc)}).encode())
        except Exception:
            _log.exception("format request crashed")
            self._send(
                500,
                "application/json",
                json.dumps(
                    {"error": "Unexpected error — details are in the docformat log file."}
                ).encode(),
            )

    # -- metadata ---------------------------------------------------------

    def _meta(self) -> dict:
        """What the front end needs to be honest up front: the active profile
        name and whether PDF export (LibreOffice) and AI assist (Ollama) can
        actually run on this machine."""
        try:
            profile_name = load_profile(self.profile_path).name
        except Exception:  # noqa: BLE001 — a bad profile shouldn't 500 the page
            profile_name = "(profile could not be loaded)"
        return {
            "profile": profile_name,
            "pdf_available": _export.soffice_available(),
            "ai_available": _ai_available(),
        }

    # -- pipeline ---------------------------------------------------------

    def _run_pipeline(self, fields: dict) -> dict:
        source = fields.get("source")
        if not source or not source[0]:
            raise ValueError("No draft .docx uploaded.")

        sid = uuid.uuid4().hex
        session = self.work_dir / sid
        session.mkdir(parents=True)
        self.sessions[sid] = session
        while len(self.sessions) > MAX_SESSIONS:  # evict + delete the oldest
            old_sid = next(iter(self.sessions))
            shutil.rmtree(self.sessions.pop(old_sid), ignore_errors=True)

        src_name = Path(source[0]).name or "draft.docx"
        src_path = session / src_name
        src_path.write_bytes(source[1])

        profile = load_profile(self.profile_path)
        template_upload = fields.get("template_docx")
        if template_upload and template_upload[0]:
            tpl_path = session / Path(template_upload[0]).name
            tpl_path.write_bytes(template_upload[1])
            profile.template_file = str(tpl_path)

        field_values = fields.get("fields")
        if field_values and field_values[1]:
            parsed = json.loads(field_values[1].decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("'fields' must be a JSON object of name -> value.")
            apply_field_values(profile, {str(k): str(v) for k, v in parsed.items()})

        use_ai = fields.get("ai", (None, b"0"))[1] == b"1"
        want_pdf = fields.get("pdf", (None, b"1"))[1] == b"1"

        src_path = _convert.ensure_docx(src_path, session)
        doc = _ingest.ingest(src_path)
        doc = _classify_ai.classify_ai(doc) if use_ai else _classify.classify(doc)

        styled = _apply.apply_styles(doc, profile, session / (src_path.stem + "_formatted.docx"))
        _elements.add_elements(styled, profile, doc)
        qa_path = _qa.write_report(doc, session / "qa_report.md")

        pdf_path = None
        if want_pdf:
            if not _export.soffice_available():
                raise RuntimeError(
                    "LibreOffice ('soffice') not found — install it or untick 'Export tagged PDF'."
                )
            pdf_path = _export.export_pdf(styled, session)

        review = [
            {
                "index": i,  # 1-based position, so the writer can find the block
                "label": b.label.value,
                "confidence": b.confidence,
                "text": b.text[:120],
            }
            for i, b in enumerate(doc.blocks, 1)
            if _qa.needs_review(b)
        ]
        return {
            "docx": f"/files/{sid}/{styled.name}",
            "pdf": f"/files/{sid}/{pdf_path.name}" if pdf_path else None,
            "qa": f"/files/{sid}/{qa_path.name}",
            "total_blocks": len(doc.blocks),
            "review": review,
            "notes": doc.notes,
        }

    # -- plumbing ---------------------------------------------------------

    def _read_multipart(self) -> dict[str, tuple[str | None, bytes]]:
        """Parse multipart/form-data into {field: (filename, bytes)}."""
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            raise ValueError("Expected multipart/form-data.")
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        raw = f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(raw)
        fields: dict[str, tuple[str | None, bytes]] = {}
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            fields[name] = (filename, payload)
        return fields

    def _send(self, code: int, ctype: str, body: bytes, download: str | None = None):
        self.close_connection = True  # one response per connection; no stuck buffers
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        if download and not download.endswith(".pdf"):  # PDFs preview in-browser
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def log_message(self, fmt, *args):  # keep the console clean; log to file
        _log.debug("%s %s", self.address_string(), fmt % args)


def make_server(profile_path: Path, port: int = 0) -> ThreadingHTTPServer:
    """Build the local-only HTTP server (port 0 = pick a free port)."""
    handler = type(
        "Handler",
        (_Handler,),
        {
            "profile_path": profile_path,
            "sessions": {},
            "work_dir": Path(tempfile.mkdtemp(prefix="docformat_gui_")),
        },
    )
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(profile_path: Path, port: int = 8765, open_browser: bool = True) -> None:
    """Run the GUI until Ctrl+C."""
    try:
        server = make_server(profile_path, port)
    except OSError:
        # Port taken — most likely docformat is already running (double-launch).
        print(
            f"Port {port} is busy (is docformat already running at "
            f"http://127.0.0.1:{port}/ ?). Starting on a free port instead."
        )
        server = make_server(profile_path, 0)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"docformat GUI running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
        shutil.rmtree(server.RequestHandlerClass.work_dir, ignore_errors=True)
