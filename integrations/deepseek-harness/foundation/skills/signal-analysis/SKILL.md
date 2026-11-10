---
name: signal-analysis
description: Fit linear calibration data, evaluate supplied calibration equations or apply declared fluorescence correction factors to experimental tables.
---

Inspect authorized CSV/TSV/XLSX data with `highzyme_inspect_table`. Select columns, units and an explicit worksheet when needed. Call `highzyme_analyze_signal`; it reuses the existing SciPy/NumPy calculations and reads data directly from the file. Do not copy long tables into tool arguments.

Choose an operation:
- `fit_calibration`: `columns: {"x":"concentration","y":"signal"}`, `parameters: {"x_unit":"uM","y_unit":"a.u."}`. Fits y = slope*x + intercept by ordinary least squares, preserving individual observations.
- `linear_readout`: `columns: {"concentrations":"concentration"}`, `parameters: {"x_unit":"uM","channels":[{"label":"channel-a","slope":2,"intercept":1,"range":[0,10],"y_unit":"a.u.","source":"a supplied calibration"}]}`. Evaluates supplied equations only inside their supplied ranges.
- `quenching_correction`: `columns: {"observed":"fluorescence","correction_factors":"factor"}`, `parameters: {}`. The first observation is the unquenched reference; correction factors must be supplied, not inferred from unspecified optics.
- `quantify`: `columns: {"signal":"signal"}`, `parameters: {"y_unit":"a.u."}`, `calibration_file: "artifacts/.../signal-calibration-result.json"`. Inverts the saved linear calibration for measured signals; values outside its concentration range return no concentration rather than automatic extrapolation. The signal unit must match the calibration. Use the same experimental/imaging basis; a numerical inverse is not an independent validation.

Keep preprocessing decisions explicit. Do not silently remove rows, average replicates, subtract blanks, extrapolate or derive a detection limit from a fitted line alone. Preserve the calibration range and relevant sample/imaging conditions when interpreting results.

Results include numeric JSON, CSV, a report and reproduction inputs. Fits include PNG/SVG curves. Use `highzyme_replot_analysis` to change plot labels without recalculation. Read the exported image when presentation matters. Use native code execution for a genuinely different analysis rather than forcing it into these operations.

For substantial independent analysis, `highzyme_delegate_research` with role `analysis` uses the shared research analysis role. Routine single-table work does not need delegation.
