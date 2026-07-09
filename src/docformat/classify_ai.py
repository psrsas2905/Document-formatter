"""OPTIONAL offline AI classifier. Same signature as classify.classify().

Strategy (hybrid, graceful degradation):
  1. Run the deterministic heuristics first — they are always the baseline.
  2. If a LOCAL Ollama server responds on localhost, ask it to re-judge only
     the blocks the heuristics were unsure about (below the QA threshold).
  3. Accept the model's answer only when it parses cleanly to a known label;
     anything else keeps the heuristic label. Every AI-assigned label is
     capped below 1.0 confidence and still appears in the QA report trail.

Nothing here ever leaves localhost, and every failure mode (server absent,
model missing, timeout, malformed reply) degrades to the heuristic result.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from . import classify as _heuristic
from .models import Block, BlockType, Document

OLLAMA_URL = os.environ.get("DOCFORMAT_OLLAMA_URL", "http://localhost:11434")
# Empty -> first locally installed model is used.
OLLAMA_MODEL = os.environ.get("DOCFORMAT_OLLAMA_MODEL", "")
PROBE_TIMEOUT_S = 2
GENERATE_TIMEOUT_S = 60

_LABELS = [t.value for t in BlockType if t is not BlockType.UNKNOWN]
# AI answers are advisory: confident enough to clear the QA threshold, but
# never as trusted as an explicit template style.
AI_CONFIDENCE = 0.75

_PROMPT = """You label paragraphs of a technical document.
Answer with EXACTLY one word from this list and nothing else:
{labels}

Paragraph:
{text}

Context: the previous paragraph was labeled {prev}.
One word answer:"""


def classify_ai(doc: Document) -> Document:
    """AI-assisted labeling with a hard fallback to heuristics."""
    doc = _heuristic.classify(doc)

    model = _pick_model()
    if model is None:
        return doc  # Ollama absent/unusable -> heuristics stand as-is

    prev_label = "None"
    for block in doc.blocks:
        if block.confidence < _heuristic.CONFIDENCE_THRESHOLD:
            _relabel(block, model, prev_label)
        prev_label = block.label.value
    return doc


def _relabel(block: Block, model: str, prev_label: str) -> None:
    prompt = _PROMPT.format(
        labels=", ".join(_LABELS), text=block.text[:500], prev=prev_label
    )
    answer = _ollama_generate(model, prompt)
    if answer is None:
        return
    answer = answer.strip().split()[0].strip(".,\"'") if answer.strip() else ""
    matched = next((lb for lb in _LABELS if lb.lower() == answer.lower()), None)
    if matched is None:
        return  # unparseable reply -> keep the heuristic label
    block.label = BlockType(matched)
    block.confidence = AI_CONFIDENCE


def _ollama_available() -> bool:
    """Return True if a local Ollama server responds. Offline-safe (localhost only)."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=PROBE_TIMEOUT_S):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _pick_model() -> str | None:
    """Configured model if set, else the first model Ollama has installed."""
    try:
        with urllib.request.urlopen(
            f"{OLLAMA_URL}/api/tags", timeout=PROBE_TIMEOUT_S
        ) as resp:
            tags = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    models = [m.get("name") for m in tags.get("models", []) if m.get("name")]
    if OLLAMA_MODEL:
        return OLLAMA_MODEL
    return models[0] if models else None


def _ollama_generate(model: str, prompt: str) -> str | None:
    """One non-streaming completion from local Ollama; None on any failure."""
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=GENERATE_TIMEOUT_S) as resp:
            return json.load(resp).get("response")
    except (urllib.error.URLError, OSError, ValueError):
        return None
