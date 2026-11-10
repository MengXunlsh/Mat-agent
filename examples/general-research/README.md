# General research examples

English · [简体中文](README.zh-CN.md)

[Application](../../README.md) · [Usage guide](../../docs/usage-guide.md)

These are synthetic software examples, not measured nanozyme experiments. Copy needed inputs into a separate research project and open it in mat-agent; outputs are saved in that project.

## Initial-rate fitting

[synthetic-initial-rates.csv](synthetic-initial-rates.csv) follows v = 2.4S/(0.3+S), without added noise.

| Setting | Value |
|---|---|
| Concentration | `substrate_mM`, mM |
| Initial rate | `initial_rate_uM_s`, μM/s |
| Expected Kₘ | 0.3 mM |
| Expected Vₘₐₓ | 2.4 μM/s |

Ask: “Use initial-rate-kinetics to fit this file. Concentration column: substrate_mM in mM; rate column: initial_rate_uM_s in μM/s. Save the result.” Inspect the curve, parameters, residuals, input and rerun code in its artifact. Inputs are already initial rates; no absorbance-time conversion or remote computation is required.

## Grouped fitting and replotting

Use [synthetic-grouped-rates.csv](synthetic-grouped-rates.csv), the same value columns, `group_columns=["material"]` and `context_columns=["pH"]`.

| Group | pH | Expected Kₘ / mM | Expected Vₘₐₓ / (μM/s) |
|---|---:|---:|---:|
| sample-a | 4 | 0.3 | 2.4 |
| sample-b | 5 | 0.6 | 1.8 |

Request an overlay or faceted plot. **Adjust curves** changes labels/layout without changing the numerical result JSON. **Revise analysis** updates the same artifact; **New analysis** or `new_analysis=true` makes an independent one.

## Evidence saving and comparison

Copy [synthetic-evidence-draft.json](synthetic-evidence-draft.json) and [synthetic-assay-source.md](synthetic-assay-source.md) together, preserving their relative locations. Ask the agent to save the draft and compare a1 with a2 from the saved JSON.

Expected: Kₘ agrees after equivalent-unit conversion, pH differs, and catalyst amount/fixed co-substrate fields are missing. Saved evidence retains values, sources and missingness rather than ranking material activity. Revise with another draft and the existing `artifact_id`; report, JSON and CSV update as one artifact.

## Calibration and sample back-calculation

[synthetic-calibration.csv](synthetic-calibration.csv) uses signal = 2 × concentration + 1. Use signal-analysis with μM and a.u. Then back-calculate [synthetic-sample-signals.csv](synthetic-sample-signals.csv): sample-a is 2 μM and sample-b is 4 μM. The final signal lies outside the calibration range and should retain that status.

## Parameterised reaction simulation

[synthetic-reaction-network.json](synthetic-reaction-network.json) describes A → B, k = 0.1 s⁻¹ and initial A = 0.001 M. Use reaction-simulation and inspect the saved time course, input parameters and units.

## Artifact versions

Save a fit, then **Reference this version** from another case in the same project. Revise/replot the original. The case report and files should retain the pinned version until **Update reference** is selected. Inspect file changes in the Versions tab.

Discussion synthesis defaults to the latest one round and allows up to 15. Its draft can be edited, collapsed and reopened. Synthesis calls the model; numerical tools run locally.

## Optional computation

- [Minimal QE execution check](qe-smoke/README.md): prepare, submit and import a small Si-cell result.
- [Common QE method inputs](qe-methods/README.md): convergence, energy combinations, electronic structure, charge, thermochemistry and NEB.

Compute examples need the user's checked and enabled resource plus compute permission. The local numerical examples above do not.
