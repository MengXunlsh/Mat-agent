---
name: assay-comparison
description: Compare material variants and assay conditions from saved literature evidence, with source-linked values, dimensional checks and explicit missing or conflicting fields.
---

Use existing evidence artifacts first. For unstructured papers, use literature-evidence to read the relevant sections and save linked records. Do not re-extract an entire paper when the requested fields are already available.

When explicitly reported stock concentrations, aliquot volumes and final assay volume are available, use formulation-calculations to derive a final concentration if it answers the comparison question. Preserve the quoted stock/preparation values in the evidence dataset and keep the derived calculation separately linked; do not relabel a calculated value as a source-reported measurement.

Establish the comparison purpose: overview, material activity, or an intended condition effect. Choose the relevant material variants and assay IDs, then call `highzyme_compare_evidence` with `selections: [{file, assay_ids}]`, `purpose`, explicit `fields`, `question` and `language`. For condition effects specify `varied_field`. Up to 12 assays can be compared together. File paths refer to saved evidence JSON, not reports.

Choose fields that matter to the user's question. For activity comparisons consider substrate and co-substrate identities/concentrations, catalyst dose and dose basis, pH, temperature, buffer, readout and normalization, plus requested outcomes. The default short field list is only an overview, not a complete activity comparison. Preserve independent material versions and assay conditions.

Canonical overview keys are `activity`, `substrate`, `pH`, `temperature`, `material_dose`, `km`, `vmax`. Use the saved observation field suffix for other requested conditions; inspect actual available fields rather than guessing. `ph`, `Km`, `Vmax` and `catalyst_concentration` are accepted aliases. Inspect returned comparison reports before making a broader claim: absent facts in a truncated snapshot mean an incomplete read. A Km value can be compared with a concentration interval only when both belong to the same varied substrate and assay branch. Neither a material name nor a formula establishes phase fractions. Read targeted full provenance for these ambiguities, without reopening every complete record.

The tool distinguishes matching/different values, missing evidence, multiple values, unreviewed facts and incompatible units. It converts compatible units only for equality checks and retains the original values in outputs. Resolve ambiguous names, numeric ranges or incompatible normalization from evidence when needed; do not guess conversions. Identical text is not a chemical identity proof. Explain relevant condition differences before comparing kinetic outcomes; do not produce an arbitrary similarity score or global ranking.

Outputs are a report, CSV and JSON with source references. Reuse the output prefix for updates; project Git retains prior versions. Use the existing artifact and file views for reading or revision. Finish with the comparison the user requested and specific remaining unknowns that affect it.

Prefer the tool-generated CSV over retyping its data. If a custom summary table is needed, use standard CSV quoting: wrap fields containing commas, line breaks or quotes in double quotes, and double any internal quote. Backslash or mathematical escaping does not quote a CSV delimiter. Check column alignment with the existing table inspector before publishing the summary.
