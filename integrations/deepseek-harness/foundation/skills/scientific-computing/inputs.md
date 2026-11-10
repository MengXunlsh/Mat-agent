# QE workflow configuration

All paths are relative to the open project. IDs use lowercase English keywords and hyphens. Atom indices are zero-based. Energies in results are eV; PW cutoffs and `conv_thr` are Ry. Supply JSON to `highzyme_qe_workflow_prepare` as `file`; resource specifications belong to the tool call, not the scientific JSON.

```json
{
  "method": "adsorption",
  "parameters": {"calculation": "scf", "ecutwfc": 50, "ecutrho": 400, "kpoints": [3, 3, 1]},
  "pseudopotentials": {"Pt": "inputs/pt.upf", "H": "inputs/h.upf"},
  "models": [
    {"id": "combined", "structure_file": "inputs/combined.extxyz"},
    {"id": "surface", "structure_file": "inputs/surface.extxyz"},
    {"id": "molecule", "structure_file": "inputs/molecule.extxyz", "parameters": {"kpoints": [1, 1, 1]}}
  ],
  "combinations": [{"id": "adsorption", "coefficients": {"combined": 1, "surface": -1, "molecule": -1}}]
}
```

The numbers above illustrate the schema, not recommended convergence settings. Model `parameters` override common parameters; nested QE namelists merge. `fixed_atoms`, `fixed_cartesian: [{index: 0, mask: [true, false, false]}]` and `magnetic_moments` are supported. Use `system`, `electrons`, `ions`, `cell` and the supported `control` fields for QE settings. The single-calculation tool accepts the same parameters and UPFs.

Method-specific fields:

- `convergence`: one model and `convergence: {parameter: "ecutwfc", values: [30, 40, 50], density_ratio: 8, tolerance_eV_atom: 0.001}`. Alternatively use `parameter: "kpoints"` and increasing grids. Differences use the last sample; a recommendation requires at least two trailing samples within tolerance. Inspect convergence of the intended property separately if total energy is insufficient.
- `adsorption` or `formation-energy`: `combinations` as above. Every combination must balance elements. Vacancy example: `defect + reservoir - perfect`, with the reservoir coefficient set by the missing atoms. Supply explicit reservoir structures; this does not implement charged-defect corrections.
- `electronic-structure`: `electronic: {model: "bulk", kpoints: [8,8,8], system: {nbnd: 20}, pdos: true, DeltaE: 0.05, pdos_groups: [{id: "metal-d", atoms: [0], orbital: "d", window_eV: [-8,0]}], bands: {points: [[0,0,0],[0.5,0,0]], labels: ["Γ","X"], points_per_segment: 20}}`. DOS energy limits are absolute QE energies; PDOS moment windows are relative to the detected Fermi/VBM reference. Optional `energy_reference_eV` overrides detection. Allowed projected orbitals must exist in the selected UPFs.
- `charge-analysis`: `charge: {coefficients: {combined: 1, component: -1}, display_model: "combined", density_kind: "all-electron", bader_models: ["combined"], isosurface: 0.002}`. `density_kind` is `valence` or PAW-only `all-electron`. Isosurface levels use electrons/bohr³. The full cube and planar profile are saved; the browser uses a smaller display grid. All components use frozen coordinates, identical cells and density grids.
- `reaction-energy`: balanced `combinations`, or `states: [{id: "reactants", coefficients: {hydrogen: 1}}, {id: "products", coefficients: {atom: 2}}]` and `reference_state: "reactants"`. Set `energy_kind: "electronic"` or `"free-energy"`. Free energy additionally requires `thermochemistry: {temperature_K: 298.15, pressure_Pa: 100000}` and each model's `vibrations`, or a sourced `thermal_correction_eV` plus `thermal_source`.
- Model vibrations: `{model: "ideal-gas", geometry: "linear", symmetrynumber: 2, spin: 0, delta_A: 0.01}` or `{model: "harmonic", indices: [0,1], delta_A: 0.01, minimum_frequency_cm1: 50}`. Ideal-gas geometries are `linear`, `nonlinear`, `monatomic`; all atoms participate. Harmonic indices select moving atoms. Displaced SCF forces form a central-difference Hessian. Extra model `corrections: [{value_eV: 0.1, source: "explicit correction convention and source"}]` are recorded separately. Do not silently clip imaginary modes.
- `neb`: two endpoint models and `neb: {initial: "initial", final: "final", images: 5, force_threshold_eV_A: 0.05, steps: 80, climb: true, interpolation: "idpp", minimum_image: false, optimizer: "broyden"}`. Same ordered atoms and cell; constraints come from the initial model. Endpoints stay fixed. `neb.x`, not `pw.x`, executes the path.

Required remote programs are detected per workflow: `pw.x`, `dos.x`, `projwfc.x`, `bands.x`, `pp.x`, `neb.x`, and optional `bader`. Configure executable overrides in the resource's `program_commands` (`dos`, `projwfc`, `bands`, `pp`, `neb`, `bader`). No executable or account is bundled into the project JSON.
