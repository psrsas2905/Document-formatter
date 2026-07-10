"""classify_ai must improve ambiguous labels when local Ollama exists and
degrade to pure heuristics in every failure mode."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from docformat import classify_ai as ai
from docformat.classify import CONFIDENCE_THRESHOLD, classify
from docformat.ingest import ingest
from docformat.models import BlockType


def test_falls_back_without_ollama(monkeypatch):
    monkeypatch.setattr(ai, "OLLAMA_URL", "http://localhost:9")  # nothing listens
    doc = ai.classify_ai(ingest("samples/input_messy.docx"))
    expected = classify(ingest("samples/input_messy.docx"))
    assert [(b.label, b.confidence) for b in doc.blocks] == [
        (b.label, b.confidence) for b in expected.blocks
    ]


class _FakeOllama(BaseHTTPRequestHandler):
    reply = "Heading2"

    def do_GET(self):  # /api/tags
        self._send({"models": [{"name": "fake-model:latest"}]})

    def do_POST(self):  # /api/generate
        self.rfile.read(int(self.headers["Content-Length"]))
        self._send({"response": self.reply})

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_ollama(monkeypatch):
    server = HTTPServer(("localhost", 0), _FakeOllama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(ai, "OLLAMA_URL", f"http://localhost:{server.server_port}")
    yield server
    server.shutdown()


def test_ai_relabels_only_uncertain_blocks(fake_ollama):
    _FakeOllama.reply = "Heading2"
    doc = ai.classify_ai(ingest("samples/input_messy.docx"))
    by_text = {b.text: b for b in doc.blocks}

    fixed = by_text["Safety Precautions"]  # the heuristically-ambiguous block
    assert fixed.label is BlockType.HEADING2
    assert fixed.confidence == ai.AI_CONFIDENCE >= CONFIDENCE_THRESHOLD

    # Confident blocks are untouched by the AI pass.
    assert by_text["Overview"].confidence == 0.9
    assert by_text["Maintenance Schedule"].confidence == 1.0


def test_garbage_reply_keeps_heuristic_label(fake_ollama):
    _FakeOllama.reply = "I think this paragraph might be a heading, maybe?"
    doc = ai.classify_ai(ingest("samples/input_messy.docx"))
    block = next(b for b in doc.blocks if b.text == "Safety Precautions")
    assert block.label is BlockType.HEADING3  # heuristic result stands
    assert block.confidence < CONFIDENCE_THRESHOLD  # still routed to QA
