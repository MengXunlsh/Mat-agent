---
name: formulation-calculations
description: Calculate units, chemical amounts, solution preparation, dilution, same-solute mixtures and mass or molar ratios from explicit inputs.
---

Use `highzyme_formulation` with `parameters` following [inputs.md](inputs.md). It calls the existing Pint arithmetic and formula parser. Supply values and units explicitly; choose either an explicit formula or a supplied molar mass when converting between mass and amount. Formula-unit amount and metal-element equivalents are different quantities.

For a short arithmetic question, return the numeric result and calculation basis without creating a document. Set an English `output_prefix` when the user requests a reusable recipe or calculation record. A missing final volume permits dilution feasibility, but does not determine an aliquot volume.

Use the user's stated purity when available. Do not infer yield, hydration, final particle composition or a solvent-volume addition rule. Ask only for information that changes the requested calculation. Use the literature/structure tools when reagent identity genuinely needs resolving.
