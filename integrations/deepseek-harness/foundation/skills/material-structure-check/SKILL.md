---
name: material-structure-check
description: Check a supplied formula, SMILES, molecular/crystal file or XYZ/EXTXYZ/POSCAR/CONTCAR coordinate model and relate its contents to the research question.
---

Identify whether the input is a formula, molecular connectivity, a crystal or macromolecular file, or a material label from a paper. A name or sample label alone is not a unique structure.

- Use `highzyme_chemical_identity` for an explicit formula or SMILES. Submit exactly one representation. Keep English formula parentheses and preserve the user's original input.
- Use `highzyme_read_structure` for authorized MOL/SDF (RDKit), CIF/mmCIF/PDB (Gemmi), or XYZ/EXTXYZ/VASP/POSCAR/CONTCAR (ASE). Report the actual parser result, including composition, atom count and cell information where available. The input must contain one coordinate model.
- If the question concerns the correspondence between a sample and a paper, use the literature evidence skill to read the relevant passage. Do not infer dopant content, oxidation state, surface termination, defects or hydration from a short label.

Explain the parts relevant to the user's question. Distinguish bulk composition, molecular connectivity and the specific structural model. For preparation of subsequent calculations, identify only missing information that affects that calculation; do not submit external jobs unless separately requested and available.

Return an identity/structure summary with the input file or representation and any concrete unresolved issue. For a reusable formula/SMILES report, give `highzyme_chemical_identity` an output_prefix so it publishes the report, numerical data and molecular drawing together; do not register these files again. Structure files can be opened directly in the project file viewer. Do not add generic scope disclaimers or create a report for every quick identity question.
