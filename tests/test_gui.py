"""End-to-end test of the local web GUI over real HTTP (localhost only)."""

import json
import threading
import urllib.request
import uuid
from pathlib import Path

import pytest

from docformat.gui import make_server


@pytest.fixture
def gui_server():
    server = make_server(Path("config/template_profile.example.yaml"), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _multipart(fields):
    boundary = uuid.uuid4().hex
    body = b""
    for name, (filename, payload) in fields.items():
        body += f"--{boundary}\r\n".encode()
        disposition = f'form-data; name="{name}"'
        if filename:
            disposition += f'; filename="{filename}"'
        body += f"Content-Disposition: {disposition}\r\n\r\n".encode()
        body += payload + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def test_index_page(gui_server):
    html = urllib.request.urlopen(f"{gui_server}/").read().decode()
    assert "docformat" in html and "Brand template" in html


def test_format_roundtrip_with_brand_template(gui_server):
    body, ctype = _multipart(
        {
            "source": ("input_messy.docx", Path("samples/input_messy.docx").read_bytes()),
            "template_docx": ("brand.docx", Path("templates/org_standard.docx").read_bytes()),
            "pdf": (None, b"0"),
            "ai": (None, b"0"),
        }
    )
    req = urllib.request.Request(
        f"{gui_server}/format", data=body, headers={"Content-Type": ctype}
    )
    data = json.load(urllib.request.urlopen(req))

    assert data["pdf"] is None
    assert data["total_blocks"] == 21
    assert [r["text"] for r in data["review"]] == ["Safety Precautions"]

    docx_bytes = urllib.request.urlopen(gui_server + data["docx"]).read()
    assert docx_bytes[:2] == b"PK"  # a real .docx zip
    qa_text = urllib.request.urlopen(gui_server + data["qa"]).read().decode()
    assert "Safety Precautions" in qa_text


def test_bad_upload_reports_error(gui_server):
    body, ctype = _multipart({"source": ("nope.docx", b"this is not a docx"), "pdf": (None, b"0")})
    req = urllib.request.Request(
        f"{gui_server}/format", data=body, headers={"Content-Type": ctype}
    )
    try:
        urllib.request.urlopen(req)
        raise AssertionError("expected HTTP 400")
    except urllib.error.HTTPError as e:
        assert e.code == 400
        assert "error" in json.load(e)


def test_download_path_traversal_blocked(gui_server):
    for path in ("/files/deadbeef/x.docx", "/files/../../etc/passwd"):
        try:
            urllib.request.urlopen(gui_server + path)
            raise AssertionError("expected HTTP 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404


def test_document_fields_fill_placeholders(tmp_path):
    """Per-document fields sent by the GUI fill cover placeholders."""
    server = make_server(Path("config/template_profile.redlotus.yaml"), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        body, ctype = _multipart(
            {
                "source": ("input_messy.docx", Path("samples/input_messy.docx").read_bytes()),
                "fields": (None, json.dumps({"Client Name": "Acme Corp",
                                             "Project No.": "RL-42"}).encode()),
                "pdf": (None, b"0"),
            }
        )
        req = urllib.request.Request(
            f"{base}/format", data=body, headers={"Content-Type": ctype}
        )
        data = json.load(urllib.request.urlopen(req))
        assert not any("[Client Name]" in n for n in data["notes"])
        assert not any("[Project No.]" in n for n in data["notes"])
        assert any("[XXXX]" in n for n in data["notes"])  # deliberately unfilled
    finally:
        server.shutdown()
