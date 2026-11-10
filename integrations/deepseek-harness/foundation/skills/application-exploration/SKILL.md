---
name: application-exploration
description: Propose evidence-grounded nanozyme application directions for a specified material or research need, including matched readout, controls and a minimal discriminating validation plan.
---

# Application exploration

Adapt to the user's requested scope. A discussion does not start a campaign. For an execution task in a case, read highzyme_case_research and configure application-exploration if appropriate. Use native planning for substantial work; keep case stages proportional to the requested deliverable.

1. Establish the material or application need, target analyte/reaction, relevant medium and operating conditions, readout, and practical constraints. Ask only for missing information that changes the proposal.
2. Use authorized project data and accessible publications. Follow publication-retrieval and literature-evidence when relevant. Save the evidence in project artifacts with usable source locators.
3. Propose a small set of concrete directions, normally 3–5 unless the user specifies otherwise. For each, explain the source-supported catalytic role, recognition/selectivity mechanism, signal chain, expected interference and compatibility gaps. Distinguish an established application, an adaptation and an unverified transfer hypothesis. Do not transfer assay values between samples or directions.
4. Review feasibility and counter-evidence. Reuse the native verification role for substantial independent review, with saved sources and a clear bounded question. Missing binding/selectivity, matrix stability or signal evidence remains an unresolved question.
5. For each retained direction, state a falsifiable hypothesis, baseline, controls, measurable criterion and the cheapest sufficient next check. Computation is optional and uses only enabled user resources. Save cards with highzyme_case_research(action="candidate", candidate={title,hypothesis,baseline,kind:"application-exploration",application,evidence_artifact_ids,uncertainties,validation:{method,comparison,criterion}}). If no case is active, publish an ordinary project report instead of converting the conversation automatically.

Stop when the requested candidate directions and relevant checks are complete. Do not expand into wet-lab execution or launch model training automatically. When actual results arrive, publish them as artifacts and use action="feedback" with candidate_id, source_artifact_id, outcome (supports/contradicts/inconclusive) and summary. Update or reject the hypothesis accordingly; preserve prior results in Git.

References for the workflow design are shared in ../material-design/references.md. These are design references, not evidence for a proposed nanozyme application.

Use candidate_id when a supported analysis or calculation tests a saved candidate; the tool records its proposal version, question and criterion. On collecting results, compare them with that criterion and record supports, contradicts or inconclusive using action="feedback" and the result artifact (plus job_id for a compute task). Keep earlier-version results attached to the tested version. A material design can supply parent_candidate_id to build on an application candidate in the same case. Native plans manage execution; case stages only organize research state.
