import { registerCalculationTools } from './calculation-tools.mjs';
import { registerComputeTools } from './compute-tools.mjs';
import { ComputeResources } from './state.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { ResearchProject, deniedTool, git } from './research.mjs';
import { caseResearch, updateCaseResearch, registerCaseResearchTools, candidateValidation, researchValidations } from './case-research.mjs';
import { artifactVisual } from './result-views.mjs';

const runtime = createRequire(new URL('../web-runtime/package.json', import.meta.url));
const { defineTool } = await import(pathToFileURL(runtime.resolve('@deepseek-ai/dsh-tools')).href);

test('case workflow preserves source versions, candidate revisions, feedback and restart state using native artifacts', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-case-research-'));
  try {
    const p = await new ResearchProject({ id: 'project', path: root }).load();
    const c = await p.createCase('Synthetic application workflow', 'application-workflow');
    await p.attachSession(c.id, 'session');
    const owner = { sessionId: 'session', caseId: c.id };
    const tools = new Map();
    registerCaseResearchTools({ tool(name, description, parameters, execute) {
      defineTool({ name, description, parameters, execute, output: { schema: { type: 'object', additionalProperties: true }, render: () => [] } }); tools.set(name, execute);
    }, requireProject: async () => p, ownerFor: () => owner, caseFor: () => c });
    const exec = { agent: { session: { id: 'session' } } };
    const configure = await tools.get('highzyme_case_research')({ action: 'configure', kind: 'application-exploration', objective: 'Compare a proposed signal chain against its substrate-free control.', language: 'en' }, exec);
    assert.match(configure.artifact.file, /cases\/application-workflow-.+\/research-plan.json$/);
    const unchanged = await tools.get('highzyme_case_research')({ action: 'configure', kind: 'application-exploration', objective: configure.objective, language: 'en' }, exec);
    assert.equal(unchanged.artifact.revision, configure.artifact.revision);
    const source = await p.publish({ title: 'Synthetic source', file: 'synthetic-source.md', content: 'Synthetic software fixture; no measured material activity.', kind: 'source' });
    const candidate = { title: 'Synthetic direction', hypothesis: 'The signal vanishes in the substrate-free control.', baseline: 'Substrate-free control',
      application: 'A hypothetical colorimetric signal chain', evidence_artifact_ids: [source.id], uncertainties: ['Matrix interference unmeasured'],
      validation: { method: 'Compare synthetic control data', comparison: 'Matched conditions', criterion: 'Predefined signal difference' } };
    const first = await tools.get('highzyme_case_research')({ action: 'candidate', candidate }, exec);
    await assert.rejects(updateCaseResearch(p, c, { action: 'candidate', candidate: { ...candidate, validation: { criterion: { slope: 2 } } } }, owner), /must be text strings/);
    assert.equal(first.candidates[0].status, 'ready_for_validation');
    const pinned = first.candidates[0].evidence[0].revision;
    await p.publish({ artifactId: source.id, content: 'Later source revision.' });
    const revised = await updateCaseResearch(p, c, { action: 'candidate', candidate: { ...candidate, id: first.candidates[0].id, title: 'Revised synthetic direction' } }, owner);
    assert.equal(revised.candidates.length, 1); assert.equal(revised.artifact.id, configure.artifact.id);
    assert.equal(revised.candidates[0].evidence[0].revision, pinned);
    const result = await p.publish({ title: 'Synthetic feedback', file: 'synthetic-result.md', content: 'Synthetic counter-example for software testing.', kind: 'result' });
    const feedback = await updateCaseResearch(p, c, { action: 'feedback', candidate_id: first.candidates[0].id, source_artifact_id: result.id, outcome: 'contradicts', summary: 'Synthetic control contradicts the hypothesis.', stage: 'validation' }, owner);
    assert.equal(feedback.candidates[0].status, 'needs_revision');
    const loaded = await new ResearchProject({ id: 'project', path: root }).load();
    assert.equal((await caseResearch(loaded, loaded.case(c.id))).stage, 'validation');
    const visual = await artifactVisual(p, { artifactId: feedback.artifact.id });
    assert.equal(visual.kind, 'research'); assert.equal(visual.tables[0].rows.length, 1);
    assert.equal((await git(root, ['status', '--porcelain', '--', c.folder + '/research-plan.json', c.folder + '/research-plan.md', '.highzyme/project.json'])).trim(), '');
    assert.match(deniedTool(p, { name: 'highzyme_case_research', arguments: { action: 'candidate' } }, root, 'read-only'), /read-only/);
    assert.equal(deniedTool(p, { name: 'highzyme_case_research', arguments: { action: 'read' } }, root, 'read-only'), undefined);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('material candidates reject explicit charge contradictions and preserve unknowns without pretending to calculate activity', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-design-check-'));
  try {
    const p = await new ResearchProject({ id: 'project', path: root }).load(), c = await p.createCase('Synthetic design');
    const owner = { sessionId: 'session', caseId: c.id };
    await updateCaseResearch(p, c, { action: 'configure', kind: 'material-design' }, owner);
    const input = { title: 'Declared Fe3O4 model', hypothesis: 'This hypothetical site model changes the readout.', baseline: 'Unmodified material', design: 'Test a declared valence model',
      composition: { formula: 'Fe3O4', species: [{ element: 'Fe', count: 3, oxidation_state: 3 }, { element: 'O', count: 4, oxidation_state: -2 }] } };
    const bad = await updateCaseResearch(p, c, { action: 'candidate', candidate: input }, owner);
    assert.equal(bad.candidates[0].status, 'rejected');
    const other = await updateCaseResearch(p, c, { action: 'candidate', candidate: { ...input, title: 'Unspecified valence', composition: { formula: 'Fe3O4' } } }, owner);
    assert.equal(other.candidates[1].screening.checks.at(-1).status, 'unknown');
    assert.equal(other.candidates[1].status, 'needs_evidence');
    await assert.rejects(updateCaseResearch(p, c, { action: 'candidate', candidate: { ...input, evidence_artifact_ids: ['missing'] } }, owner), /source artifact/);
    await p.setAccess({ ...p.access, write: [] });
    await assert.rejects(updateCaseResearch(p, c, { action: 'stage', stage: 'review' }, owner), /access/);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('validation follows the tested proposal through local analysis, QE preparation and later candidate revisions', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-validation-'));
  try {
    const p = await new ResearchProject({ id: 'project', path: root }).load(), c = await p.createCase('Synthetic linked research');
    await p.attachSession(c.id, 'session');
    const owner = { sessionId: 'session', caseId: c.id };
    await updateCaseResearch(p, c, { action: 'configure', kind: 'application-exploration', objective: 'Synthetic software check', constraints: ['Synthetic data only'] }, owner);
    const evidence = await p.publish({ title: 'Synthetic evidence', kind: 'source', file: 'source.md', content: 'Software fixture.' });
    const app = { title: 'Synthetic application', hypothesis: 'A synthetic signal distinguishes the control.', baseline: 'Synthetic blank', application: 'Synthetic colorimetry', evidence_artifact_ids: [evidence.id], validation: { method: 'Linear synthetic calibration', comparison: 'Matched synthetic points', criterion: 'A slope of two' } };
    const first = await updateCaseResearch(p, c, { action: 'candidate', candidate: app }, owner);
    const parent = first.candidates[0];
    await updateCaseResearch(p, c, { action: 'configure', kind: 'material-design' }, owner);
    const design = { ...app, kind: 'material-design', title: 'Synthetic site model', application: undefined, design: 'Declared model for software checking', parent_candidate_id: parent.id };
    const saved = await updateCaseResearch(p, c, { action: 'candidate', candidate: design }, owner), candidate = saved.candidates[1];
    assert.equal(candidate.based_on.candidate_revision, parent.proposal_revision);
    assert.deepEqual(candidate.research_context.constraints, ['Synthetic data only']);
    const tools = new Map(), tool = (name, description, parameters, execute) => tools.set(name, execute);
    registerCalculationTools({ tool, requireProject: async () => p, ownerFor: () => owner });
    await fs.writeFile(path.join(root, 'calibration.csv'), 'x,y\n0,1\n1,3\n2,5\n3,7\n');
    const exec = { agent: { session: { id: 'session' } } };
    const analysis = await tools.get('highzyme_analyze_signal')({ candidate_id: candidate.id, validation_comparison: 'Supplied synthetic calibration points only', file: 'calibration.csv', operation: 'fit_calibration', columns: { x: 'x', y: 'y' }, parameters: { x_unit: 'uM', y_unit: 'a.u.' }, language: 'en' }, exec);
    assert.equal(analysis.artifact.validation.candidate_revision, candidate.proposal_revision);
    assert.equal(analysis.artifact.validation.criterion, 'A slope of two');
    assert.equal(analysis.artifact.validation.comparison, 'Supplied synthetic calibration points only');
    const distinct = await candidateValidation(p, { candidate_id: candidate.id, validation_question: 'A separate calibration question' }, owner);
    assert.equal(distinct.comparison, null);
    assert.equal(analysis.summary.slope, 2);
    const resources = new ComputeResources(path.join(root, 'state'), {}); await resources.load();
    await resources.configure({ id: 'ssh', transport: 'ssh', host: 'unused-software-fixture' });
    await fs.copyFile(new URL('../../../examples/general-research/qe-smoke/silicon.extxyz', import.meta.url), path.join(root, 'silicon.extxyz'));
    await fs.writeFile(path.join(root, 'si.upf'), '<UPF><PP_HEADER element="Si" /></UPF>');
    registerComputeTools({ tool, resources, requireProject: async () => p, ownerFor: () => owner });
    const job = await tools.get('highzyme_qe_prepare')({ candidate_id: candidate.id, resource_id: 'ssh', structure_file: 'silicon.extxyz', pseudopotentials: { Si: 'si.upf' }, parameters: { calculation: 'scf', ecutwfc: 20, ecutrho: 80, kpoints: [1,1,1] } }, exec);
    assert.equal(job.status, 'prepared'); assert.equal(job.validation.candidate_revision, candidate.proposal_revision);
    const revised = await updateCaseResearch(p, c, { action: 'candidate', candidate: { ...design, id: candidate.id, hypothesis: 'A changed synthetic hypothesis.' } }, owner);
    assert.notEqual(revised.candidates[1].proposal_revision, candidate.proposal_revision);
    const feedback = await updateCaseResearch(p, c, { action: 'feedback', candidate_id: candidate.id, source_artifact_id: analysis.artifact.id, outcome: 'supports', summary: 'Synthetic slope matches the old criterion.' }, owner);
    const row = feedback.candidates[1];
    assert.equal(row.feedback[0].candidate_revision, candidate.proposal_revision);
    assert.equal(row.validation_outcome, 'not_validated');
    const uncertain = await p.publish({ title: 'Synthetic inconclusive result', kind: 'result', file: 'uncertain.md', content: 'Synthetic uncertainty.', validation: await candidateValidation(p, { candidate_id: row.id }, owner) });
    const current = await updateCaseResearch(p, c, { action: 'feedback', candidate_id: row.id, source_artifact_id: uncertain.id, outcome: 'inconclusive', summary: 'No discriminating outcome.' }, owner);
    assert.equal(current.candidates[1].validation_outcome, 'inconclusive');
    assert.equal(current.candidates[1].status, 'ready_for_validation');
    await assert.rejects(updateCaseResearch(p, c, { action: 'feedback', candidate_id: parent.id, source_artifact_id: uncertain.id, outcome: 'supports', summary: 'Wrong target' }, owner), /different candidate/);
    await assert.rejects(tools.get('highzyme_compute_submit')({ candidate_id: 'missing', resource_id: 'ssh', capability: 'python', script: 'unused' }, exec), /retained candidate/);
    const links = await researchValidations(p, c);
    assert.equal(links.tasks.length, 1); assert.equal(links.results.length, 2);
    const restored = await new ResearchProject({ id: 'project', path: root }).load();
    assert.equal((await caseResearch(restored, restored.case(c.id))).candidates[1].validation_outcome, 'inconclusive');
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});
