---
name: scientific-computing
description: Prepare, run and visualize structure optimization, convergence, adsorption and formation energies, electronic structure, charge analysis, thermochemistry and NEB with user-connected Quantum ESPRESSO resources.
---

Reuse the native project, permissions, task, artifact and Git mechanisms. Use `compute-resource-setup` for connection or software setup. Calculations use the user's enabled resource; preparation and postprocessing run locally. Do not invent scientific settings or substitute a generated number for an executed calculation.

## Select and prepare

Read the relevant structures, UPFs and existing results. Establish the target quantity, reference states, units, magnetic state, boundary conditions and accuracy needed for this task. Ask only for missing choices that affect the result. Use `highzyme_qe_prepare` for SCF, `relax` or `vc-relax`; use `highzyme_qe_workflow_prepare` with a project JSON configuration for the methods below. See [inputs.md](inputs.md) for the exact configuration contract.

- Optimization and convergence: preserve intended fixed atoms or Cartesian components. Optimize positions with `relax`, positions and cell with `vc-relax`. Check electronic and geometry convergence separately. Test cutoffs and k-point density for the target energy or property before interpreting small differences.
- Adsorption/binding: calculate the combined system and explicit components with consistent settings. Use signed coefficients, usually combined minus surface minus adsorbate. State the sign convention, geometry treatment, coverage and reference state.
- Defects/site stability: supply explicit stoichiometrically balanced energy combinations and chemical reservoirs. A computed energy difference does not establish an equilibrium defect concentration. Charged-defect finite-size and potential-alignment corrections require a separate explicit treatment; this adapter does not generate them automatically.
- Electronic structure: SCF then dense-grid NSCF then DOS/PDOS, with an explicit reciprocal-space band path when requested. Record Fermi/VBM/user energy reference. Orbital centers are first moments in an explicitly selected integration window; select actual atom indices and orbitals, not a material-wide label.
- Charge analysis: use frozen component geometries and identical simulation cells, origins and grids. Difference density is an explicit signed sum. For all-electron Bader partitioning use PAW reconstruction and a sufficiently fine grid. Inspect charge integration and convergence before interpretation. The Bader executable is a user-resource dependency, not an embedded charge model.
- Reaction/free energy: provide balanced states or energy combinations. Electronic energies and finite-temperature corrections remain separate. Ideal-gas thermochemistry needs geometry, symmetry number, spin, temperature and pressure; adsorbate harmonic thermochemistry needs the selected moving atoms and an explicit low-frequency treatment if necessary. Use optimized structures and inspect imaginary modes. Solvent, electrochemical and standard-state corrections must be supplied with their source and convention.
- NEB/CI-NEB: endpoints must use the same ordered atoms, cell and constraints. Supply optimized endpoints, image count and a path-force threshold. Inspect the path and convergence before reporting a barrier. A NEB energy barrier is not automatically an activation free energy or rate constant.

## Execute and collect

Show the prepared method, stages, source files, effective scientific parameters and requested resource specifications. Existing authorization to run the calculation is sufficient; do not ask again for the same scope. Submit with `highzyme_qe_submit` using its durable job ID. Use status/cancel and collect on that ID; never replay an ambiguous submission. Stage programs and missing dependencies are checked before submission. QE stages use the resource's Shell/MPI environment; only generic Python jobs need a configured remote Python.

Use `highzyme_qe_collect` when the job ends. It retains inputs, source hashes, outputs and diagnostics, and publishes the complete result group as one artifact. Inspect saved numerical tables, exported figures and structures. Read or replot saved results without rerunning a completed calculation. Retain failed tasks as failed; change the input and prepare a new task only when a new calculation is needed. Distinguish a small execution example from a converged material result.

Keep results linked to material/structure identity, settings, references, scheduler job and artifact Git version. Computations can be prepared in any research mode.

When testing a saved case candidate, pass candidate_id and, when needed, validation_question and validation_criterion to the preparation tool. The prepared task and collected artifact retain that proposal version. After collection, evaluate the saved criterion and use highzyme_case_research(action="feedback", candidate_id, job_id, source_artifact_id, outcome, summary); do not interpret a completed task as support by itself.
