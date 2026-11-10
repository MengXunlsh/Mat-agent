import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { registerComputeTools, reconcileComputeJobs, updateComputeJob } from './compute-tools.mjs';
import { resourcePolicy, resourceRequest } from './resource-policy.mjs';
import { ComputeResources } from './state.mjs';
import { ResearchProject, deniedTool } from './research.mjs';

const runtime = createRequire(new URL('../web-runtime/package.json', import.meta.url));
const { defineTool } = await import(pathToFileURL(runtime.resolve('@deepseek-ai/dsh-tools')));

test('native Harness compiles compute tools; project and execution grants apply before input staging', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hz-compute-'));
  try {
    const p = await new ResearchProject({ id: 'project', path: root }, { shell: true, network: true, compute: false }).load();
    const resources = new ComputeResources(path.join(root, 'local-state'), {});
    await resources.load();
    const resource = await resources.configure({ id: 'ssh', transport: 'ssh', host: 'example-cluster' });
    assert.equal(resource.enabled, false);
    assert.equal((await fs.readFile(resources.file, 'utf8')).includes('PRIVATE KEY'), false);
    const tools = new Map();
    registerComputeTools({ tool(name, description, parameters, execute) {
      defineTool({ name, description, parameters, execute, output: { schema: { type: 'object', additionalProperties: true }, render: () => [] } });
      tools.set(name, execute);
    }, resources, requireProject: async () => p, ownerFor: () => ({ sessionId: 'session' }) });
    const exec = { agent: { session: { id: 'session' } } };
    assert.equal((await tools.get('highzyme_compute_resources')({}, exec)).permitted, false);
    assert.match(deniedTool(p, { name: 'highzyme_qe_submit' }, root), /Enable external/);
    assert.match(deniedTool(p, { name: 'highzyme_qe_workflow_prepare' }, root, 'read-only'), /read-only/);
    assert.match(deniedTool(p, { name: 'highzyme_qe_test' }, root), /Enable external/);
    assert.match(deniedTool(p, { name: 'highzyme_compute_setup', arguments: { action: 'save' } }, root, 'read-only'), /read-only/);
    await assert.rejects(tools.get('highzyme_qe_submit')({ resource_id: 'ssh' }, exec), /Enable external/);
    p.operations.compute = true;
    p.fileAccess.denyRead = ['private.csv'];
    await assert.rejects(tools.get('highzyme_compute_submit')({ resource_id: 'ssh', files: [{ file: 'private.csv' }] }, exec), /Grant read access/);
    await fs.writeFile(path.join(root, 'binary.dat'), Buffer.from([255, 254, 0, 128]));
    resources.rows.push({ id: 'http', transport: 'http' });
    await assert.rejects(tools.get('highzyme_compute_submit')({ resource_id: 'http', files: [{ file: 'binary.dat' }] }, exec), /UTF-8 text/);
    p.operations.network = false;
    assert.match(deniedTool(p, { name: 'highzyme_compute_setup', arguments: { action: 'inspect' } }, root), /Network access/);
    await assert.rejects(tools.get('highzyme_qe_test')({ resource_id: 'ssh' }, exec), /network access/);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('scientific workflows prepare real inputs, retain source ownership, and publish collected groups', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hz-workflow-'));
  try {
    const p = await new ResearchProject({ id: 'project', path: root }, { shell: true, network: true, compute: false }).load();
    await fs.copyFile(new URL('../../../examples/general-research/qe-smoke/silicon.extxyz', import.meta.url), path.join(root, 'silicon.extxyz'));
    await fs.writeFile(path.join(root, 'si.upf'), '<UPF><PP_HEADER element="Si" /></UPF>');
    await fs.writeFile(path.join(root, 'workflow.json'), JSON.stringify({ method: 'convergence', parameters: { ecutwfc: 30, kpoints: [1,1,1] }, pseudopotentials: { Si: 'si.upf' },
      models: [{ id: 'silicon', structure_file: 'silicon.extxyz' }], convergence: { parameter: 'ecutwfc', values: [20,30], tolerance_eV_atom: .01 } }));
    const resources = new ComputeResources(path.join(root, 'state'), {}); await resources.load();
    await resources.configure({ id: 'ssh', transport: 'ssh', host: 'example-cluster' });
    const tools = new Map();
    registerComputeTools({ tool: (name, _d, _p, execute) => tools.set(name, execute), resources, requireProject: async () => p, ownerFor: () => ({ sessionId: 'session' }) });
    const exec = { agent: { session: { id: 'session' } } };
    p.fileAccess.denyRead = ['si.upf'];
    await assert.rejects(tools.get('highzyme_qe_workflow_prepare')({ resource_id: 'ssh', file: 'workflow.json' }, exec), /Grant read access/);
    p.fileAccess.denyRead = [];
    const job = await tools.get('highzyme_qe_workflow_prepare')({ resource_id: 'ssh', file: 'workflow.json' }, exec);
    assert.equal(job.status, 'prepared'); assert.equal(job.sessionId, 'session'); assert.deepEqual(job.qe.required_programs, ['pw']);
    const folder = path.join(root, job.qe.folder);
    const fixture = await fs.readFile(new URL('../../../tests/fixtures/qe-silicon-scf.out', import.meta.url));
    for (const stage of job.qe.stages) await fs.writeFile(path.join(folder, stage.id, 'qe.out'), fixture);
    await fs.writeFile(path.join(folder, 'workflow-status.json'), JSON.stringify({ status: 'completed' }));
    const complete = { ...job, status: 'completed', files: ['sample-1/qe.out','sample-2/qe.out','workflow-status.json'] };
    resources.downloadMany = async (_resource, id, files, destination) => { assert.equal(id, job.id); assert.equal(destination, folder); assert.equal(files.length, 3); };
    await p.saveJob(complete);
    const { collectWorkflow } = await import('./workflow-tools.mjs');
    const value = await collectWorkflow(p, resources, complete, complete);
    assert.equal(value.status, 'completed'); assert.equal(value.artifact.sessionId, 'session');
    assert.ok(value.artifact.revision);
    assert.ok(value.artifact.files['structure_sample-1']);
    assert.ok(value.artifact.relatedFiles.includes(job.qe.folder + '/sample-2/qe.out'));
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('saved resource defaults apply per rank and job limits reject oversized overrides', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hz-compute-policy-'));
  try {
    const resources = new ComputeResources(root, {});
    await resources.load();
    const row = await resources.configure({ id: 'ssh', transport: 'ssh', host: 'example-cluster',
      defaults: { ranks: 2, threads: 3, memory_mb: 2048, timeout_seconds: 600 }, limits: { ranks: 4, threads: 8, memory_mb: 4096, timeout_seconds: 1200 } });
    assert.deepEqual(resourceRequest(row, {}), { ranks: 2, threads: 3, memory_mb: 2048, timeout_seconds: 600 });
    assert.equal(resourceRequest(row, { cores: 5 }).threads, 5);
    for (const key of ['ranks', 'threads', 'memory_mb', 'timeout_seconds']) assert.throws(() => resourceRequest(row, { [key]: row.limits[key] + 1 }), /limit exceeded/);
    assert.throws(() => resourcePolicy({ defaults: { ranks: 4 }, limits: { ranks: 2 } }), /Default exceeds/);
    assert.throws(() => resourcePolicy({ defaults: { threads: 1.5 } }), /Invalid resource/);
    const restored = new ComputeResources(root, {}); await restored.load();
    assert.deepEqual(restored.get('ssh').defaults, row.defaults);
    assert.deepEqual(restored.get('ssh').limits, row.limits);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('setup works without a project; QE preparation stays local, respects grants and cancels without remote calls', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hz-qe-prepare-'));
  try {
    const p = await new ResearchProject({ id: 'project', path: root }, { shell: true, network: true, compute: false }).load();
    await fs.copyFile(new URL('../../../examples/general-research/qe-smoke/silicon.extxyz', import.meta.url), path.join(root, 'silicon.extxyz'));
    await fs.writeFile(path.join(root, 'si.upf'), '<UPF><PP_HEADER element="Si" /></UPF>');
    const resources = new ComputeResources(path.join(root, 'state'), {}); await resources.load();
    await resources.configure({ id: 'ssh', transport: 'ssh', host: 'example-cluster', defaults: { ranks: 2, memory_mb: 2048 } });
    const tools = new Map(); let setupArguments, projectRequired = false;
    const adapter = registerComputeTools({ tool: (name, _description, _parameters, execute) => tools.set(name, execute), requireProject: async () => { projectRequired = true; return p; },
      resources, ownerFor: () => ({ sessionId: 'source' }), setupPermission: () => false, setupResource: async (_action, args) => { setupArguments = args; return { saved: true }; } });
    const exec = { agent: { session: { id: 'source' } } };
    await tools.get('highzyme_compute_resources')({}, exec);
    await tools.get('highzyme_compute_setup')({ action: 'save', host: 'example-cluster' }, exec);
    assert.equal(projectRequired, false); assert.equal(setupArguments.setupSessionId, 'source');
    const job = await tools.get('highzyme_qe_prepare')({ resource_id: 'ssh', structure_file: 'silicon.extxyz', pseudopotentials: { Si: 'si.upf' }, parameters: { calculation: 'scf', ecutwfc: 20, kpoints: [1, 1, 1] } }, exec);
    assert.equal(job.status, 'prepared'); assert.equal(job.resources.ranks, 2); assert.equal(job.qe.request.parameters.ecutrho, 80);
    assert.match(await fs.readFile(path.join(root, job.qe.folder, 'qe.in'), 'utf8'), /ecutwfc/);
    assert.equal((await p.jobs()).length, 1);
    await assert.rejects(adapter.submitQE(p, job.id), /Enable external/);
    p.operations.compute = true;
    await fs.appendFile(path.join(root, job.qe.folder, 'qe.in'), '\nchanged');
    await assert.rejects(adapter.submitQE(p, job.id), /inputs changed/);
    const cancelled = await updateComputeJob(p, resources, job.id, 'cancel');
    assert.equal(cancelled.status, 'cancelled'); assert.equal(cancelled.collection_status, 'skipped');
    await reconcileComputeJobs(p, resources);
    assert.equal((await p.jobs())[0].collection_attempts, undefined);
    p.fileAccess.denyRead = ['silicon.extxyz'];
    await assert.rejects(adapter.prepareQE(p, { resource_id: 'ssh', structure_file: 'silicon.extxyz', pseudopotentials: { Si: 'si.upf' } }, { sessionId: 'source' }), /Grant read/);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('interrupted result imports retry finitely and retain the scheduler ID without submission', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hz-compute-recovery-'));
  try {
    const p = await new ResearchProject({ id: 'project', path: root }).load();
    await p.saveJob({ id: 'job-existing', type: 'compute', status: 'completed', scheduler_id: '123', resource_id: 'ssh', qe: { folder: 'outputs/test' } });
    let queries = 0;
    const resource = { request: async (_id, route) => { assert.equal(route, '/jobs/job-existing'); queries++; throw new Error('connection offline'); } };
    for (let n = 0; n < 4; n++) await reconcileComputeJobs(p, resource);
    const [job] = await p.jobs();
    assert.equal(queries, 3);
    assert.equal(job.scheduler_id, '123');
    assert.equal(job.collection_status, 'failed');
    assert.equal(job.last_error, 'connection offline');
    assert.equal(p.data.artifacts.length, 0);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});
