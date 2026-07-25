# Document Delta & Grounded Chat

A runnable engineering-document comparison system that ingests native or scanned PDFs, converts them to a typed canonical representation, aligns reordered pages and elements, detects meaningful changes, produces three report formats, and answers questions only from cited evidence.

## Features

- Persistent PID/revision/checksum metadata in SQLite
- PyMuPDF native extraction; 300-DPI Tesseract OCR with word boxes and confidence warnings
- Adapter interface shared by native PDF, scanned PDF, and a documented DWG stub
- Page matching by text and dimensions; element matching by fuzzy text, numeric/entity, type, and spatial signals using Hungarian assignment
- Added, removed, modified, and moved deltas with evidence, confidence breakdown, and deterministic severity
- Typed pressure, flow, temperature, length, diameter, stage, speed, percentage, and identifier extraction
- Diagnostic separation for punctuation, numbering, likely OCR noise, and uncertain alignment
- JSON, Markdown, and HTML reports; mock grounded chat with validated delta citations and refusal
- JSON traces, correlation IDs, stage timing, error visibility, and `/metrics`
- React/TypeScript UI, generated sample pairs, tests, evaluation, Docker

## Quick start

Python 3.11+ is required.

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/generate_samples.py
uvicorn apps.api.main:app --reload
```

Frontend, in another terminal:

```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:5173. There is no login. Mock chat needs no API key. Or run everything with `docker compose up --build`.

### Groq chat provider

Create a local `.env` (it is gitignored) and add:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_rotated_groq_key
GROQ_MODEL=llama-3.3-70b-versatile
```

Restart Uvicorn after changing the environment. Groq is used only after deterministic retrieval. Its output must be valid JSON, all returned citation IDs are checked against retrieved delta evidence, and unsupported citations or uncited factual answers are rejected. Set `LLM_PROVIDER=mock` to restore fully offline operation.

## Windows and OCR

Install Tesseract (for example with `winget install UB-Mannheim.TesseractOCR`) and set `TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe` in `.env`. Native PDFs work without it. Missing OCR returns a readable configuration error and never silently drops content.

## Commands

`make install`, `make samples`, `make run`, `make test`, `make eval`, and `make demo`. On PowerShell use the corresponding Python commands above if GNU Make is unavailable. Tests: `python -m pytest`. Evaluation: `python -m eval.run_eval`.

## API flow

POST multipart PDF and revision to `/api/v1/documents` twice; POST their PIDs to `/api/v1/comparisons`; retrieve `/delta` or `/report/{json|markdown|html}`; POST `{"question":"What changed?"}` to `/chat`. Interactive documentation is at http://localhost:8000/docs.

## Canonical and alignment design

Documents contain PID, revision, checksum, warnings, pages, and processing metadata. Pages retain dimensions and elements. Elements retain original and normalized text (numbers are never removed), page, absolute/normalized boxes, extraction method/confidence, numeric values, units, identifiers, and type. Normalization ignores whitespace-only changes.

Pages are assigned one-to-one using fuzzy page text and dimensions, allowing insertion, removal, and reordering. Bounded element candidates use normalized text, token overlap, engineering identifiers, numeric overlap, unit/type compatibility, and spatial region. Dimension-to-text pairs, conflicting identifiers, unrelated low-overlap blocks, and ambiguous short tokens are rejected before SciPy Hungarian assignment. Content change wins over movement; unchanged content beyond the configured distance is moved.

Engineering values are parsed deterministically with raw text, normalized value, numeric value, unit, type, context, and source element. Significance rules keep numeric, unit, identifier, safety, and operational changes in the main report while punctuation/numbering noise remains available under `ignored_deltas`. Severity and severity reasons are deterministic.

## LLM boundary

No LLM performs extraction, numeric comparison, bounding-box comparison, assignment, significance, severity, or structured retrieval. Broad summaries plus page, dimension, note, identifier, severity, and change-type queries are deterministic. Optional Groq synthesis is limited to open descriptive questions after evidence selection; returned IDs are validated and answer confidence uses only cited evidence. Mock mode is fully offline and reproducible.

## Evaluation and observability

Samples are generated locally with PyMuPDF; pair 1 contains a dimension change, added note, removed ID, and moved block; pair 3 includes page insertion/reordering and table/note changes. `make eval` compares expected and observed change types, prints precision/recall/F1, records chat citation/refusal checks, and saves `data/reports/evaluation.json`. The known failure is split/merged OCR blocks. Tests include the complete upload -> compare -> reports -> cited chat -> refusal flow.

Every comparison/chat saves `data/traces/<trace-id>.json`; `/metrics` reports comparisons, chat, retrieval, failures, delta counts, and latency buckets.

## Trade-offs, scope cuts, and scaling

Visual markup, semantic geometry, advanced tables, and a production LLM provider are honest scope cuts; markup returns 501. For 500-sheet production documents, move ingestion to workers, store artifacts in object storage, cache per-page canonical data, use approximate candidate indexes and page-parallel matching, persist vectors, stream progress, cap candidate neighborhoods, and keep trace/metric backends outside the app process. Add ODA/ezdxf, learned layout/table models, regression datasets from reviewed customer documents, access control, encryption, retention policies, and human review for low-confidence deltas.
