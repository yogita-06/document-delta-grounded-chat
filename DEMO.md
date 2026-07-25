# 3–5 minute demo

1. Upload `data/samples/pair1_rev_a.pdf` and `pair1_rev_b.pdf`. Explain that samples are generated and have labeled engineering changes.
2. Run comparison. Point out backend-derived meaningful, ignored-noise, severity, and change-type counts.
3. Select the **high** filter. Open the 100 bar → 120 bar numeric modification and show evidence/confidence.
4. Open the HTML report. Show the executive summary and diagnostic separation.
5. Ask **What changed?** Show the bounded numbered summary and sentence-level citations.
6. Ask **Which dimensions changed?** Show pressure, flow, and stage evidence.
7. Ask **Which notes were added?** Point out that extracted text is shown without invention.
8. Ask **What changed on page 1?** Explain deterministic page metadata filtering.
9. Ask **Which equipment IDs changed?** Show exact identifier retrieval.
10. Ask **Who created this drawing?** Show confidence zero, no citations, and grounded refusal.
11. Open the returned trace ID and show routing, filtering, reranking, citation, and confidence spans.
12. Run `python -m eval.run_eval`; open JSON and Markdown scorecards and mention the documented split/merge limitation.
