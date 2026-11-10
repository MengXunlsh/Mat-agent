---
name: literature-evidence
description: Read supplied research papers and supporting information to answer a focused question or extract source-linked material, assay and application evidence.
---

Use `highzyme_read_document` for PDF pages and DOCX blocks; use native reading for text. Begin with the user's question and selected files. Read the returned coverage and locators; an excerpt is not the entire paper. Empty text requires image reading or a request for a readable source, not invented content.

## Focused reading
Read only the sections needed to answer the question, extending the page range when necessary. Cite the project-relative file and exact returned locator, with the DOI if the document provides it. Preserve numbers and units as printed. Save a note only when requested or needed as a reusable deliverable.

## Structured extraction
Use the field conventions and role boundaries below for structured extraction, adapted from mat-agent's existing extraction workflow. Keep distinct papers, material versions, assays and endpoints separate. Start with tested material identities, then connect the relevant preparation, measurement and application facts.

For a small input, extract directly. For multiple papers or substantial independent sections, delegate bounded work with the native subagent tool. Supply the authorized files, already established material names, requested fields and output format. A checking subagent is useful for ambiguous or cross-document claims; four fixed agents are not required.

Use `highzyme_delegate_research` with role `literature` for the maintained extraction role, or `verification` for independent evidence review. It reuses native Harness subagents; tasks appear in the existing project task list. Supply a separate English output path for each independent assignment. Use `highzyme_research_task` to wait for/cancel a task and read its final summary. The literature role returns a JSON draft for normal evidence saving; it does not publish unreviewed draft facts automatically.

For scanned pages or essential figures, call `highzyme_render_document` on 1 to 4 needed PDF pages and use native `read_image` on its PNG files. The selected model must accept images. Keep the original PDF page locator and source hash when recording visual evidence; rendering a page is not OCR or scientific interpretation. Image files can be read directly with the native image tool. Use publication-retrieval when a specifically identified paper/SI must first be saved locally.

Check extracted claims against the actual cited passages. Preserve unresolved conflicts and missing fields without filling them from general knowledge. Read figures with the available image tool when they are essential; label values estimated from plots separately from printed measurements.

Return a concise answer for focused reading. For reusable structured evidence, read [evidence-schema.md](evidence-schema.md), write a draft JSON with native file tools, then call `highzyme_evidence_save`. It publishes JSON, CSV and a readable report together, with material/assay links, source positions and Git history. Quote matching checks transcription and source location; it does not certify the interpretation or experimental validity.

Use one scalar condition or result per fact where practical. Preserve raw values, units and precision. Reuse the existing output prefix for a revision; read its JSON into a separate draft, revise the relevant facts, and save again. Keep other facts and source identifiers intact. Save the JSON and report as reusable project artifacts.

Role boundaries:
- Material: actual sample names, composition, morphology, variants and reported preparation.
- Assay: activity, substrate, conditions, readout and kinetic results for each distinct measurement.
- Application: demonstrated use, analyte, tested sample and application performance; distinguish these from introductory motivation.
- Verification: confirm the cited passage supports the fact, material version and assay association; identify conflicting values or missing evidence.

For paired main text and supporting information, retain the source file for every fact. Do not merge different variants or assay conditions solely because they share a material name. Describe any disagreement explicitly rather than selecting a value without explanation.
