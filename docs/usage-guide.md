# mat-agent usage guide

English · [简体中文](usage-guide.zh-CN.md)

[Application](../README.md) · [Examples](../examples/general-research/README.md)

The base mode is general research. Cases organise general research, application exploration or material design. Material-family methods are skills on the same agent foundation.

## Task execution

DeepSeek Harness supplies conversations, model connections, plans, context compression, files and Shell, persistent terminals, background tasks, subagents and interface components. The mat-agent plugin manages research state, artifacts, permissions, database access and computation. Python modules parse documents/structures, analyse numerical inputs and generate figures.

```text
Research request → Main agent and relevant skills → Tools/subagents
  → Inputs, numbers, code, figures, report and sources
  → One artifact group and a Git version → Case references or validation feedback
```

Conceptual questions receive an answer; execution requests initiate operations. Case stages organise research content while native plans manage execution. Small tasks do not need every stage.

## First use

Launch `scripts/start_workbench.ps1 -OpenBrowser` from the root; the default port is 8790. Change it with `-Port` and stop with Ctrl+C in the launch terminal. Installation commands are in the [main README](../README.md).

Add a model connection and default model in settings. The composer selector affects the current conversation; existing conversations retain their own model. Subagents inherit the main model unless configured otherwise. Web search is configured separately.

Add a real local directory as a project. New conversations and cases inherit the current or most recent project. Missing project/model information produces a message and preserves the draft. Copy example inputs to a separate research project before trying them.

## Projects and artifacts

Conversations and cases are peers in a project. Conversations support discussion, reading, coding and standalone analysis. Cases add goals, candidates, evidence, validation feedback and a dedicated directory.

The project panel follows the current project, providing files, artifacts, permissions, tasks, archive and memory. The file view supports browsing, preview and editing. One artifact groups its report, data, figures, code and sources.

**Organise discussion into an artifact** uses a native subagent. The main-view action uses the open conversation/case and defaults to the latest one round, adjustable to 15 rounds. In project artifacts, select a source conversation and individual messages. Lists show brief previews; synthesis uses the selected complete text. Edit and save the draft to publish it. The panel can collapse while retaining unsaved content.

New filenames use lowercase English keywords and hyphens; titles and prose follow the user's language. Revisions keep the artifact ID and path. Use **New analysis** or `new_analysis=true` for an independent analysis, and `artifact_id` to revise an existing result. Replotting changes layout/labels while preserving fitted numerical results.

## Permissions

| Location | Controls |
|---|---|
| Project resources → Permissions | Read/write access to project files, folders and complete artifact groups |
| Settings → Execution permissions | Shell, networking, external computation and new-conversation defaults |
| Native conversation selector | Read-only, project modification and full-access modes |

Conversations, cases and subagents share project file rules. Restricting paths or disabling networking also disables general Shell execution: a host process cannot enforce those per-file/per-request rules. File tools continue using authorised paths. Project memory is disabled when document access is restricted.

Permission changes govern subsequent reads. Already-sent content remains in conversation history. Full-access mode still works together with explicitly configured content and execution rules.

## Versions, references, archive and memory

The **Versions** tab shows Git nodes, timestamps, messages and file differences for the current conversation/case. Restore/revert previews the affected files and creates a new commit. Conflicting later changes stop the operation with a message. Native isolated workspaces support creation, switching, comparison and merging under `.agents/worktrees/`.

**Reference this version** pins the entire artifact group and commit. Later revisions do not change existing references; **Update reference** switches them explicitly. Previews and downstream tools use the same pinned files. Read-only reference caches are generated when local file paths are needed.

Project archive manages conversations and cases with restore, trash and permanent deletion. Deletion retains published artifacts; deleting a case directory is a separate option. Git history remains. Resolve active tasks before deleting their context.

Project memory is off by default. Enabled agents can save, retrieve and update adopted decisions, preferences and methods. Users can view, edit and delete entries. It uses project-isolated keyword retrieval in `.highzyme/memory.jsonl`; complete reports remain artifacts.

## Skills and scientific tools

Skills provide method guidance; tools perform structured reads, calculations and persistence. The agent selects methods, interprets results and revises them. Choose skills with `/` or describe the task directly.

| Skill | Purpose |
|---|---|
| literature-evidence | Material, sample, assay and source evidence from publications and supplements |
| publication-retrieval | Accessible full text, abstracts and supported supplements by DOI/PMCID/PMID |
| nanozyme-dataset | Query/read/save database records and use registered material spaces |
| assay-comparison | Compare conditions, numbers, units, sources and missing information |
| material-structure-check | Check formulae, SMILES and molecular/crystal/coordinate files |
| initial-rate-kinetics | Single/grouped Michaelis–Menten fitting of initial rates |
| formulation-calculations | Units, formulations, dilution, mixing and reagent ratios |
| signal-analysis | Calibration, sample back-calculation, readout conversion and fluorescence correction |
| image-colorimetry | Image regions, RGB/HSV measurements and region annotations |
| reaction-simulation | Parameterised models and mass-action integration |
| scientific-plotting | Consistent scientific figures, replotting and editable exports |
| discussion-artifact | Discussion synthesis into revisable artifacts |
| application-exploration | Evidence-based applications, readouts, controls and validation questions |
| material-design | Hypothesis-led designs using family methods and explicit criteria |
| compute-resource-setup | Assist with user resource connections, environment and minimal execution tests |
| scientific-computing | Prepare/manage supported multistep QE workflows |

The 16 skills are in `integrations/deepseek-harness/foundation/skills`. Literature, analysis, verification and discussion synthesis use native subagents with the same model and permission mechanisms.

Read PDF/DOCX by pages or text blocks. Scans require rendered pages and an image-capable model. Formulae/SMILES use identity tools; RDKit reads MOL/SDF, Gemmi reads CIF/mmCIF/PDB, and ASE reads XYZ/EXTXYZ/VASP/POSCAR/CONTCAR. Formats are constrained at each tool's entry. A name alone does not define a unique structure.

Initial-rate fitting requires concentration/rate columns and units; select a worksheet for multi-sheet Excel files. Rate standard deviations are optional. Groups are fitted separately with consistent within-group conditions. Inputs are already measured initial rates, not raw absorbance time series. Replicates are retained; figure, parameters, input, report and rerun code form one artifact.

Plots use white backgrounds, consistent categorical colours, mathematical labels/units, SVG and high-resolution PNG. Opening a preview reads saved results rather than rerunning fits or calculations.

## Data sources and evidence

### Project files

Use **Project panel → Files** to locate local research files, then grant the agent access under **Permissions**. Built-in tools accept CSV, TSV or XLSX for analyses such as calibration, supported structure formats such as CIF or XYZ for structure inspection, and PDF or DOCX for document reading. Select a tool based on the file type and the task. You can export records from another database to a table and use them in the same way.

### Optional structured nanozyme dataset

This connector expects the nanozyme data layout and registry. The current release has no built-in direct connector for arbitrary SQLite or PostgreSQL databases or external materials databases.

Connect a compatible local `database_registry.json` under **Settings → Tools & compute → Nanozyme data**. The `HIGHZYME_DATASET_REGISTRY` environment variable is also supported. Project data browsing becomes available after a successful connection.

Dataset tools cover catalogs, filtering, material–version–assay details, individual reads and evidence saving: `highzyme_dataset_catalog/search/material/read/save`. Saved evidence is complete; model reads use compact observations and sources, with details available on demand. Missingness, original values, units, conditions and source locators are retained.

Connect a compatible material-space registry in the same settings or set `HIGHZYME_MATERIAL_SPACE_REGISTRY`. Two-dimensional coordinates support visualization. Similarity queries use the registered descriptors.

The reader reuses verified data and recent query matches; pagination changes only the slice. Versions and the five asset hashes must match. Data stays read-only; selected evidence and analyses are written to user projects.

### Literature evidence

Literature evidence uses `highzyme.evidence.v1`. `highzyme_evidence_save` saves structurally checked drafts, and `highzyme_compare_evidence` compares 2–12 selected assays, retaining units, multiple values, missing context and conflicts. A database snapshot is distinct from rereading the publication; artifacts preserve the actual source scope.

## Case research and validation

Application exploration considers catalytic function, targets, recognition/selectivity, signal chains and interference. Material design considers composition, sites, coordination, surfaces, supports and morphology. Both share agents, plans, tools, artifacts and versions.

Plans save goals, constraints, candidates, fixed-version evidence, unknowns, methods, controls and criteria. `highzyme_candidate_check` checks consistency such as charge balance only for explicitly supplied composition, stoichiometry and oxidation states; names do not generate adsorption energies, stability or activity numbers. Family guidance depends on reaction, coordination, spin and conditions.

Candidates have stable `candidate_id` values and content versions. Local analyses, generic computation and QE preparation can link validation questions and criteria. Actual results record supports/contradicts/inconclusive with their artifact and Git version. Old feedback remains associated with the old plan version. `parent_candidate_id` can connect a material candidate to an application candidate in the same case.

## Optional external computation

Add SSH/Slurm or compatible HTTP resources in settings. The setup assistant opens a conversation to inspect the connection, queue, working directory, software modules and executables. It uses the default model and preserves existing drafts and active tasks.

SSH uses local OpenSSH configuration, a private key or SSH agent, and known_hosts. Local SSH tools handle fingerprints and encrypted keys; private-key text is not sent to the model. Login nodes need Python 3.6+, tar and Slurm. Compute nodes use Shell/MPI and do not run mat-agent.

Check the writable directory, queue/account and executables before enabling the resource and compute permission. Recheck after an application restart. Slurm availability alone does not establish that every QE/postprocessing program is ready.

| Method | Main requirements |
|---|---|
| SCF and structure/cell relaxation | `pw.x`, structure, UPF, cutoffs, k points, constraints and magnetic moments |
| Cutoff/k-point convergence | Explicit sequences and criteria, preserving each step's energy |
| Adsorption/binding/formation energies | Explicit reference states and coefficients; elemental balance; no automatic charged-defect correction |
| DOS/PDOS/bands | `dos.x`, `projwfc.x`, `bands.x` and matching inputs |
| Charge difference/Bader | `pp.x`, matching component cells/grids; PAW for all-electron density; user-provided Bader executable |
| Reaction/free energies | Separate electronic, vibrational and temperature/pressure terms; imaginary-mode and reference-state checks |
| NEB/CI-NEB | `neb.x`, matching atom order/cell/endpoints and path convergence |

Use `highzyme_qe_prepare` for single calculations or `highzyme_qe_workflow_prepare` for multistep JSON. Preparation creates inputs and a request. Review, then submit/query/cancel/collect using the same `job_id`; changed inputs need new preparation.

Defaults are 1 MPI process, 1 thread, 1024 MiB and 300 seconds, adjustable with limits in settings and subject to the queue. Normal completion stops early; the time limit bounds occupancy and runaway jobs.

The background reconciler checks existing job IDs after restart rather than resubmitting. Stopping a conversation does not cancel a remote job. Retry failed collection without recomputing. Scheduler completion, electronic/structural convergence and collection have separate states. Local terminal processes last only for the current service lifetime.

Direct adapters support SSH/Slurm/QE and compatible HTTP, not PBS/LSF. Users provide software and pseudopotentials. See [workflow fields](../integrations/deepseek-harness/foundation/skills/scientific-computing/inputs.md) and [QE examples](../examples/general-research/qe-methods/README.md).

## Storage and trial

```text
user-project/
  .git/                              file history
  .highzyme/                         indexes, permissions, tasks, memory, reference caches
  artifacts/<discussion-keywords>/    conversation artifacts
  cases/<keywords>-<short-id>/        case inputs and research content
    artifacts/                       case artifacts
  inputs/                            research inputs, or other user folders

application/runtime/foundation/home/  model connections, conversations and local settings
```

Files are read/written in the selected project directory. Existing paths are not automatically renamed. Revisions update the same files through Git. Memory, permissions, task caches and runtime settings have separate Git exclusions; project Git alone is not a backup of all state. Application runtime records are stored under `runtime/`.

Run `scripts/check_foundation.py` from the root for offline software and numerical checks.

A manual trial can follow: default model → add project → fit synthetic initial rates → inspect artifact group → synthesise one discussion round → create case and pin result version → revise original and inspect pinned files → inspect/restore Git changes → try archive, memory and compute settings as needed. [Examples](../examples/general-research/README.md) provide expected values. Model synthesis uses the selected API; remote computation needs the user's enabled resource and permission.
