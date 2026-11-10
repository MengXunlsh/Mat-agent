# Minimal QE execution check

English · [简体中文](README.zh-CN.md)

[General examples](../README.md) · [Compute guide](../../../docs/usage-guide.md)

A two-atom diamond Si primitive cell with Γ-only SCF checks input preparation, Slurm submission, QE execution, convergence parsing and artifact import. It does not establish production cutoffs or k-point accuracy.

## Prepare and run

1. Copy this directory's structure and parameter inputs to your research project.
2. Obtain the Si UPF from the [official QE library](https://pseudopotentials.quantum-espresso.org/upf_files/Si.pbe-rrkj.UPF), retaining its URL and SHA-256.
3. Configure your resource in settings or with compute-resource-setup. Check SSH/Slurm, the writable directory, queue and `pw.x`. Enable the resource and external-compute permission.
4. Pass the structure, parameters and `{"Si":"<project-relative-UPF-path>"}` to `highzyme_qe_prepare`. This small check can use 1 MPI process, 1 thread, 1024 MiB and 300 seconds.
5. Review inputs/request, then submit/query/collect with the returned `job_id`. The background reconciler also checks active jobs and imports completed QE results.

Inspect scheduler status, normal QE termination, electronic convergence and artifact completeness separately. Retry collection if a download fails instead of submitting again.

## Resource ownership

Queue, account, software modules, MPI and executables belong to the user's resource configuration. mat-agent generates inputs and processes results; QE and pseudopotentials are not bundled in this example. Use appropriate structures, spin, potentials and convergence settings for quantitative work.
