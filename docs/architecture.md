# Architecture

Read `PROJECT_SPEC.md` first. This doc is a quick map.

## Data flow

    source.docx
       │  ingest.py        -> Document(blocks, hints)
       ▼
    classify.py            -> blocks labeled (heuristics)  [classify_ai.py optional]
       │
       ▼  apply.py         -> styled .docx (template named styles)
       │  elements.py      -> headers/footers, page numbers, TOC
       ▼  export.py        -> tagged PDF (LibreOffice headless)
    qa.py                  -> qa_report.md (what a human must review)

## Key principle

The **template profile** (`config/*.yaml` + its `.dotx`) is the source of truth.
We map content onto existing named styles; we never invent formatting.

## Offline guarantee

Nothing in the core path touches the network. The only optional AI path talks to a
**local** Ollama server and always falls back to heuristics if it is absent.
