# Evidence dataset

Write a JSON object using `schema: "highzyme.evidence.v1"`, optional `title` and `question`, and these arrays (nonempty, at most 300 rows each):

- `materials`: `{id, name, version?}`. Each reported variant gets its own material ID.
- `assays`: `{id, material_id, label}`. Separate conditions, substrates and measurement series.
- `facts`: `{id, material_id, assay_id?, field, value_raw, unit_raw, review, evidence}`.

IDs are unique within each array. `value_raw` and `unit_raw` are strings, preserving the printed value and units. Use `review: "supported"` only after reading evidence and checking its association with this material and assay; otherwise use `needs_review` or `conflict`. Repeated/conflicting facts are retained rather than silently averaged or selected.

Use field names consistently: `activity`, `substrate`, `co_substrate`, `pH`, `temperature`, `time`, `material_dose`, `substrate_concentration`, `co_substrate_concentration`, `buffer`, `buffer_concentration`, `wavelength`, `readout`, `normalization`, `dose_basis`, `km`, `vmax`. Other fields such as preparation or morphology are allowed. Each assay condition belongs to that assay; do not infer it from a different measurement.

`evidence` contains one or more `{file, locator, quote, source_sha256?, basis?}` entries. Paths are project-relative authorized files. For PDF use `PDF/page[3]`; for DOCX use the exact reader locator, e.g. `word/document.xml/paragraph[2]`; for TXT/Markdown use `lines[4:6]`. `quote` must be a verbatim excerpt at that position; only whitespace differences are normalized. The optional SHA-256 binds the source version. The tool records a source hash for every saved reference.

Default `basis` is `text`. For a figure actually inspected visually, use `basis: "visual"` and a descriptive transcription in `quote`. The tool checks the source location but does not verify visual content; do not describe that mechanical check as visual verification. Label digitized estimates as such in the value and review.

Example fact:
```json
{"id":"f1","material_id":"m1","assay_id":"a1","field":"km","value_raw":"0.30","unit_raw":"mM","review":"supported","evidence":[{"file":"sources/assay-note.md","locator":"lines[2]","quote":"Km = 0.30 mM"}]}
```

For comparison, select saved evidence JSON paths and assay IDs with `highzyme_compare_evidence`. The comparison preserves these raw values and references. Missing information stays absent.
