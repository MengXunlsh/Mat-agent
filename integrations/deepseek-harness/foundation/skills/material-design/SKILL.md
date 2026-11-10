---
name: material-design
description: Develop nanozyme material design candidates from a target application and evidence, with family-specific descriptors, explicit assumptions, physical consistency checks and a matched validation plan.
---

# Material candidate design

For a discussion, explain options without starting a workflow. For an authorized case task, read highzyme_case_research and configure material-design when appropriate. Continue from existing evidence and candidates; use native planning and bounded research subagents rather than starting another agent framework.

1. Define the target reaction/application, required conditions and readout, practical synthesis constraints and baseline. Prefer a concrete sample/version to a pooled material name.
2. Use authorized project data and accessible publications. Follow publication-retrieval and literature-evidence when relevant. Save the evidence in project artifacts with usable source locators.
3. Read families.md for the relevant material family. Generate a small, chemically interpretable set of changes to composition, coordination, carrier, defect/site, surface or morphology. Preserve the distinction between a specified structure and a composition-only hypothesis. State the mechanism being tested and what would falsify it.
4. Check what can actually be checked. highzyme_candidate_check verifies explicit stoichiometry and charge using supplied species counts and oxidation states, including mixed valence. It does not infer valence, spin, eg occupancy, phase stability or activity. Unsupported or missing inputs remain unknown. Retain source-dependent descriptor criteria with their applicable family, reaction, coordination, spin and experimental conditions; never use a universal eg target or apply a perovskite tolerance rule to spinels.
5. Review the hypotheses and counter-evidence. For substantial independent review, use the existing verification role with the candidate plan and source artifact files; revise the creator's proposal after examining the review. Do not require multiple agents for a small question.
6. Choose a discriminating validation plan with a baseline, changed variable, measured outcome and acceptance/rejection criterion. Use existing kinetic, signal, structural, evidence-comparison or scientific-computing tools when relevant. External calculation requires an enabled compatible resource; prepare inputs without claiming execution when unavailable.

Save candidates through highzyme_case_research(action="candidate") with title, hypothesis, baseline, kind="material-design", design, evidence_artifact_ids, uncertainties, validation:{method,comparison,criterion}, and optional composition:{formula,species:[{element,count,oxidation_state}],target_charge}. The save path recomputes declared composition checks. Proposal completeness and validation outcome are stored separately.

Publish actual validation outputs first, then link them using action="feedback". A contradiction returns the candidate for revision. Reuse the same candidate ID and artifact paths for a revision; an independent alternative gets a new ID. Complete the requested deliverable without forcing DFT or wet-lab validation into every task.

Use candidate_id when a supported analysis or calculation tests a saved candidate; the tool records its proposal version, question and criterion. On collecting results, compare them with that criterion and record supports, contradicts or inconclusive using action="feedback" and the result artifact (plus job_id for a compute task). Keep earlier-version results attached to the tested version. A material design can supply parent_candidate_id to build on an application candidate in the same case. Native plans manage execution; case stages only organize research state.
