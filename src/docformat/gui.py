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
import re
import sys
import tempfile
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import apply as _apply
from . import classify as _classify
from . import convert as _convert
from . import classify_ai as _classify_ai
from . import elements as _elements
from . import export as _export
from . import ingest as _ingest
from . import qa as _qa
from .classify import CONFIDENCE_THRESHOLD
from .template import apply_field_values, load_profile

_ASSET = Path(__file__).parent / "assets" / "gui.html"

_CONTENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".md": "text/markdown; charset=utf-8",
}


def default_profile_path() -> Path | None:
    """Find the example profile: working dir first, then a PyInstaller bundle."""
    candidates = [Path("config/template_profile.example.yaml")]
    if getattr(sys, "_MEIPASS", None):  # PyInstaller onefile extraction dir
        candidates.append(Path(sys._MEIPASS) / "config" / "template_profile.example.yaml")
    for c in candidates:
        if c.exists():
            return c
    return None


class _Handler(BaseHTTPRequestHandler):
    server_version = "docformat"
    protocol_version = "HTTP/1.1"  # keep-alive; we always send Content-Length
    profile_path: Path  # set by serve()
    sessions: dict[str, Path]  # sid -> output dir
    work_dir: Path

    # -- routing ---------------------------------------------------------

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", _ASSET.read_bytes())
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
        if self.path != "/format":
            self._send(404, "text/plain", b"not found")
            return
        try:
            fields = self._read_multipart()
            result = self._run_pipeline(fields)
            self._send(200, "application/json", json.dumps(result).encode())
        except Exception as exc:  # surface the reason to the page, not a stack trace
            self._send(400, "application/json", json.dumps({"error": str(exc)}).encode())

    # -- pipeline ---------------------------------------------------------

    def _run_pipeline(self, fields: dict) -> dict:
        source = fields.get("source")
        if not source or not source[0]:
            raise ValueError("No draft .docx uploaded.")

        sid = uuid.uuid4().hex
        session = self.work_dir / sid
        session.mkdir(parents=True)
        self.sessions[sid] = session

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
            {"label": b.label.value, "confidence": b.confidence, "text": b.text[:120]}
            for b in doc.blocks
            if b.confidence < CONFIDENCE_THRESHOLD
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

    def log_message(self, fmt, *args):  # keep the console clean
        pass


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
    server = make_server(profile_path, port)
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
