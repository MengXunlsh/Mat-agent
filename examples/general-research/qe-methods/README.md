# Small inputs for common QE methods

English · [简体中文](README.zh-CN.md)

[General examples](../README.md) · [Minimal execution check](../qe-smoke/README.md) · [Workflow fields](../../../integrations/deepseek-harness/foundation/skills/scientific-computing/inputs.md)

These inputs check execution and artifact import. Copy them to a user project's `inputs/`, configure your resource and obtain the required UPF files. Try one method at a time.

## Pseudopotentials

Save each at the path referenced by its JSON, retaining its source and hash:

- `si.upf`: [Si PBE RRKJ](https://pseudopotentials.quantum-espresso.org/upf_files/Si.pbe-rrkj.UPF).
- `h.upf`: [H PBE RRKJ](https://pseudopotentials.quantum-espresso.org/upf_files/H.pbe-rrkjus_psl.1.0.0.UPF).
- `h-paw.upf`: [H PBE PAW](https://pseudopotentials.quantum-espresso.org/upf_files/H.pbe-kjpaw_psl.1.0.0.UPF).

## Inputs

| Input | Inspect |
|---|---|
| `convergence.json` | Two cutoffs for small Si₂; step energies and differences, not a production convergence series |
| `adsorption.json` | H₂ binding relative to two spin-polarised H atoms; references, coefficients and sign, not surface adsorption |
| `electronic-structure.json` | Si₂ DOS, projections and a short Γ–X path; energy reference and projection grouping |
| `charge-analysis.json` | H₂/frozen-atom difference density, PAW all-electron density and optional Bader; matching cells/grids |
| `formation-energy.json` | Small Si-vacancy energy combination with a specified Si reference; not a dilute-defect model |
| `reaction-energy.json` | H₂ → 2H electronic energy and ideal-gas free energy at 298.15 K, 1 bar; modes and corrections |
| `neb.json` | Three-image constrained collinear H + H₂ exchange; endpoints, atom order and path convergence |

Use scientific-computing and pass the selected JSON to `highzyme_qe_workflow_prepare`. Review the request, then submit/query/collect by its original `job_id`. Missing programs are reported before submission. Bader is an optional program on the user's resource.

For single structure optimisation, `highzyme_qe_prepare` supports `relax` and `vc-relax`. See [workflow fields](../../../integrations/deepseek-harness/foundation/skills/scientific-computing/inputs.md) for parameters, paths, zero-based atom indices and units.

These are execution checks. Quantitative research requires suitable geometry, spin, pseudopotentials and property-specific convergence.
