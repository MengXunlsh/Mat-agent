---
name: nanozyme-dataset
description: Find and read reported nanozyme material and assay records in the connected local structured dataset, then save selected evidence to the current project.
---

# Nanozyme dataset

Start with `highzyme_dataset_catalog`: section="overview" for counts, "filters" for the actual material/application categories and source dataset values, or "fields" for field definitions. Search also supports material_class, application_major, application_subcategory, application_direction, source_dataset, version, assay, reactant and Celsius temperature_min/temperature_max. Related stage conditions are matched within the same stage by the existing reader.

Use `highzyme_dataset_material(material_id, limit, offset)` to inspect bounded material/version/record links. Use `highzyme_material_space` when a matching analysis resource is connected: catalog, profile, neighbors or applications. Specify an unambiguous material_id or choose from CLARIFY matches. Neighbor ranks use the registered high-dimensional descriptor method, not UMAP distances. Request independent_only=true for source-independent analogies; application-transfer proposals still require evidence review and validation.

Use `highzyme_dataset_search` for a bounded first pass (default 5 records, maximum 30). Filter by `material`, `activity` (POD, CAT, OXD, SOD or the reported name), `substrate`, `ph`, `source_doi`, or `record_kind` (`measurement`, `kinetic`, `unpaired_information`, `all`). Require available quantities with `required_fields`: `km`, `vmax`, `catalyst_concentration`. Follow `page.next_offset` only when more results are needed.

For evidence you will retain, call `highzyme_dataset_save` directly: it reads and saves the complete record and returns all selected values in a concise `record` view. Do not separately read and save the same selection. For inspection without saving, use `highzyme_dataset_read`. Default detail="values" preserves every selected observation, raw unit, context, source URL and locator while omitting verbose lineage. Request detail="full" with specific `fields` from `available_fields` when original quotes, identity conflicts or substrate pairing need checking. A full read is still bounded to the selected record, not the entire material. Preserve each material, version, record and assay identity. Do not merge conditions across records or treat an associated DOI as a read paper.

Use `highzyme_dataset_save` to retain a relevant record as a Git-versioned source artifact. Use existing project files and the assay-comparison or literature-evidence skills for further comparison. Do not copy the entire dataset into the project or inject all records into model context.

Saved dataset JSON files work directly with `highzyme_compare_evidence`: select the project-relative artifact file and its original `selection.assay_id`. Use canonical comparison fields such as `activity`, `substrate`, `pH`, `temperature`, `material_dose`, `km`, `vmax`; detailed field lists belong in assay-comparison. The adapter retains raw values/units and keeps `source_document_read=false`. A truncated historical snapshot is an incomplete read, not proof the paper omitted the quantity. Do not infer phase fractions or substrate pairing from a material name or an unrelated concentration range. Historical source paths are provenance metadata, not permission to read outside the project.

If the connection is missing, ask the user to select `database_registry.json` in Settings > Tools and compute resources > Nanozyme dataset. No external API, embeddings or compute connection is needed.
