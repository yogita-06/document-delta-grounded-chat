# Submission Audit

Baseline recorded before the polish pass:

- Backend entry point: `apps/api/main.py`; frontend entry point: `apps/web/src/main.tsx`.
- Comparison, reporting, retrieval, chat, and tracing were concentrated in `src/orchestration/service.py`.
- Canonical models existed, but engineering values were only untyped number/unit lists.
- Page alignment used whole-page fuzzy text and dimensions; element assignment scored every pair and lacked hard candidate rejection.
- Delta output had no subtype, significance reason, severity reason, or diagnostic/ignored collection.
- Punctuation and numbering changes could enter the main report; split/merge support was absent.
- Chat supported broad/page/type keywords but not robust page variants, entity filters, severity filters, or the requested response schema.
- Citation validation checked ID existence but not current-comparison ownership or citation use in the answer.
- Traces existed but stage coverage was coarse and span timestamps lacked a final end time.
- Evaluation measured only presence of four change categories, producing an unrealistically perfect but weak score.
- Tests covered four broad paths but not significance, structured routing, page bounds, entity queries, or diagnostics.
- Frontend chat worked, but confidence lacked percentage/label and citations lacked evidence detail.
- Reports were safe from HTML injection but lacked executive grouping and diagnostic separation.
- Upload validation lacked a size limit and relied primarily on extension.

Baseline commands passed: 4 pytest tests, sample generation, frontend build, and the original evaluation command. The weaknesses above are correctness and evidence-quality gaps despite that green baseline.
