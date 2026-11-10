import fs from 'node:fs/promises';
import { candidateParameters, candidateValidation } from './case-research.mjs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, randomUUID } from 'node:crypto';
import { isUtf8 } from 'node:buffer';
import { checkedPath } from './research.mjs';
import { runPython } from './science.mjs';
import { resourceRequest } from './resource-policy.mjs';
import { prepareWorkflow, collectWorkflow } from './workflow-tools.mjs';

export const sshFields = {
  host: { type: 'string', description: 'SSH hostname or existing SSH config alias' }, port: { type: 'integer' },
  user: { type: 'string' }, identity_file: { type: 'string', description: 'Local private-key path; never supply key contents' },
  remote_root: { type: 'string' }, partition: { type: 'string' }, account: { type: 'string' }, qos: { type: 'string' },
  setup_script: { type: 'string', description: 'User-approved environment initialization, such as module purge/load' },
  qe_command: { type: 'string' }, python_command: { type: 'string' }, mpi_command: { type: 'string' },
  program_commands: { type: 'object', additionalProperties: true, description: 'Optional executable overrides: dos, projwfc, bands, pp, neb, bader' },
};
const resourcesSchema = { timeout_seconds: { type: 'integer' }, cores: { type: 'integer' }, memory_mb: { type: 'integer' }, ranks: { type: 'integer' }, threads: { type: 'integer' } };
const policySchema = { type: 'object', additionalProperties: false, properties: Object.fromEntries(['ranks', 'threads', 'memory_mb', 'timeout_seconds'].map(key => [key, { type: 'integer' }])) };

function inputFiles(project, files = []) {
  return files.map(row => {
    const file = typeof row === 'string' ? row : row.file;
    if (!project.permitted(file)) throw new Error('Grant read access to: ' + file);
    return { source: checkedPath(project.root, file), target: typeof row === 'string' ? path.posix.basename(file) : row.target || path.posix.basename(file) };
  });
}

export async function updateComputeJob(p, resources, id, action = 'status', signal) {
  const record = (await p.jobs()).find(j => j.id === id && j.type === 'compute');
  if (!record) throw new Error('Compute task not found');
  if (record.status === 'prepared') {
    const next = action === 'cancel' ? { ...record, status: 'cancelled', collection_status: 'skipped' } : record;
    if (action === 'cancel') await p.saveJob(next);
    return next;
  }
  const result = await resources.request(record.resource_id, '/jobs/' + id + (action === 'cancel' ? '/cancel' : ''), action === 'cancel' ? {} : undefined, signal);
  const next = { ...record, ...result, checkedAt: Date.now() };
  await p.saveJob(next); return next;
}

export async function reconcileComputeJobs(p, resources) {
  const ended = ['completed', 'failed', 'timed_out', 'cancelled'];
  for (const job of (await p.jobs()).filter(j => j.type === 'compute' &&
    (['queued', 'running', 'submission_unknown'].includes(j.status) || j.qe && !j.artifactId && j.collection_status !== 'skipped' && ended.includes(j.status) && (j.collection_attempts || 0) < 3))) {
    try {
      const next = ended.includes(job.status) ? job : await updateComputeJob(p, resources, job.id);
      if (next.qe && !next.artifactId && ended.includes(next.status)) {
        await p.saveJob({ ...next, collection_status: 'running' });
        await collectQE(p, resources, job.id, (p, id, action, signal) => updateComputeJob(p, resources, id, action, signal));
      }
    } catch (error) {
      const current = (await p.jobs()).find(j => j.id === job.id);
      const attempts = current.qe && ended.includes(current.status) ? (current.collection_attempts || 0) + 1 : 0;
      await p.saveJob({ ...current, last_error: error.message, ...(attempts ? { collection_attempts: attempts, collection_status: attempts < 3 ? 'pending' : 'failed' } : {}) });
    }
  }
}

export function registerComputeTools({ tool, requireProject, ownerFor, resources, jobUpdate, setupResource, setupPermission }) {
  tool('highzyme_compute_resources', 'List user-owned compute resources and their detected capabilities. Computation requires an enabled resource and project compute permission.', {}, async (_args, exec) => {
    return { permitted: setupPermission ? setupPermission(exec) : (await requireProject(exec)).access.compute, resources: resources.list() };
  });
  tool('highzyme_compute_setup', 'Use the compute-resource-setup skill to inspect or configure user-owned SSH/Slurm resources. Inspect is read-only; save records a local profile. Never request key contents. This tool does not submit test computations.', {
    action: { type: 'string', required: true, enum: ['inspect', 'save', 'check', 'enable', 'disable'] },
    id: { type: 'string' }, name: { type: 'string' }, defaults: policySchema, limits: policySchema, ...sshFields,
  }, async (args, exec) => {
    return setupResource(args.action, { ...args, transport: 'ssh', setupSessionId: exec.agent.session.id });
  });
  tool('highzyme_compute_submit', 'Submit an authorized script to an enabled resource, staging only selected project input files. Returns a durable job ID. Use highzyme_qe_submit for structured Quantum ESPRESSO tasks.', {
    resource_id: { type: 'string', required: true }, capability: { type: 'string', required: true }, script: { type: 'string', required: true },
    files: { type: 'array', items: { type: 'object', additionalProperties: false, properties: { file: { type: 'string', required: true }, target: { type: 'string' } } } }, ...candidateParameters, ...resourcesSchema,
  }, async (args, exec) => {
    const p = await requireProject(exec);
    const validation = await candidateValidation(p, args, ownerFor(p, exec.agent.session));
    const inputs = inputFiles(p, args.files);
    let task = { ...args, input_files: inputs };
    if (resources.get(args.resource_id).transport !== 'ssh') {
      task.files = Object.fromEntries(await Promise.all(inputs.map(async f => {
        const data = await fs.readFile(f.source);
        if (!isUtf8(data)) throw new Error('HTTP compute inputs must be UTF-8 text; use SSH for binary files');
        return [f.target, data.toString('utf8')];
      })));
      delete task.input_files;
    }
    const result = await resources.submit(args.resource_id, task, exec.signal);
    const record = { ...result, validation, resource_id: args.resource_id, ...ownerFor(p, exec.agent.session), type: 'compute', capability: args.capability };
    await p.saveJob(record); return record;
  });
  for (const action of ['status', 'cancel']) tool('highzyme_compute_' + action, 'Read or cancel an existing project compute job. Never resubmits the calculation.', {
    job_id: { type: 'string', required: true },
  }, async (args, exec) => jobUpdate(await requireProject(exec), args.job_id, action, exec.signal));
  tool('highzyme_compute_download', 'Download a selected output from a recorded job to its originating project/case.', {
    job_id: { type: 'string', required: true }, file: { type: 'string', required: true },
  }, async (args, exec) => {
    const p = await requireProject(exec), record = (await p.jobs()).find(j => j.id === args.job_id && j.type === 'compute');
    if (!record) throw new Error('Task not found');
    const c = record.caseId && p.case(record.caseId), rel = (c ? c.folder + '/' : '') + 'outputs/' + record.id + '/' + args.file;
    const target = checkedPath(p.root, rel); if (!p.permitted(rel, 'write')) throw new Error('Output path is not writable');
    const value = await resources.download(record.resource_id, record.id, args.file, target, exec.signal);
    return { ...value, file: rel };
  });
  const prepareQE = async (p, args, owner, signal) => {
    const validation = await candidateValidation(p, args, owner);
    const resource = resources.get(args.resource_id);
    if (resource.transport !== 'ssh') throw new Error('Select an SSH/Slurm resource for this QE adapter');
    const request = resourceRequest(resource, args);
    const sources = [args.structure_file, ...Object.values(args.pseudopotentials)];
    inputFiles(p, sources);
    let folder = path.posix.dirname(await p.artifactPath({ title: 'Quantum ESPRESSO', fileStem: 'qe-report', ...owner })) + '/qe-calculation';
    const base = folder;
    for (let n = 2; await fs.access(checkedPath(p.root, folder)).then(() => true, () => false); n++) folder = base + '-' + n;
    for (const file of ['qe.in', 'input.extxyz', 'request.json', 'report.md', 'result.json', 'qe.out', 'final.extxyz', 'final.cif', 'stdout.log', 'stderr.log', 'submit.sh', ...Object.keys(args.pseudopotentials).map(s => 'pseudo/' + s.toLowerCase() + '.upf')]) {
      if (!p.permitted(folder + '/' + file, 'write')) throw new Error('Grant write access to: ' + folder + '/' + file);
    }
    const directory = checkedPath(p.root, folder);
    const prepared = await runPython('highzyme.compute.qe_calculation', { ...args, action: 'prepare', directory,
      structure_file: checkedPath(p.root, args.structure_file), pseudopotentials: Object.fromEntries(Object.entries(args.pseudopotentials).map(([k, f]) => [k, checkedPath(p.root, f)])) }, signal);
    const inputs = prepared.input_files.map(f => ({ file: folder + '/' + f.target, target: f.target, sha256: f.sha256 }));
    const row = { id: 'job-' + randomUUID().replaceAll('-', ''), status: 'prepared', created_at: Date.now() / 1000, ...owner,
      validation, label: 'Quantum ESPRESSO · ' + prepared.request.structure.formula, type: 'compute', capability: 'quantum_espresso', resource_id: resource.id,
      resources: request, qe: { folder, sources, inputs, request: prepared.request, language: args.language || 'en' } };
    await p.saveJob(row); return row;
  };
  const submitQE = async (p, id, signal) => {
    if (!p.access.compute || !p.access.network) throw new Error('Enable external computation and network access in execution permissions');
    const job = (await p.jobs()).find(j => j.id === id && j.qe);
    if (!job) throw new Error('Prepared QE calculation not found');
    if (job.status !== 'prepared') return job;
    const resource = resources.get(job.resource_id);
    const inputs = inputFiles(p, job.qe.inputs);
    for (const [i, file] of inputs.entries()) {
      const digest = createHash('sha256').update(await fs.readFile(file.source)).digest('hex');
      if (digest !== job.qe.inputs[i].sha256) throw new Error('Prepared inputs changed. Prepare the calculation again before submitting: ' + job.qe.inputs[i].file);
    }
    const result = await resources.submit(resource.id, { ...job.resources, job_id: job.id, capability: 'quantum_espresso', input_files: inputs,
      ...(job.qe.workflow ? { launch_mode: 'workflow', required_programs: job.qe.required_programs, script: 'bash workflow-runner.sh' } : { script: (resource.qe_command || 'pw.x') + ' -in qe.in > qe.out 2>&1' }) }, signal);
    const next = { ...job, ...result }; await p.saveJob(next); return next;
  };
  tool('highzyme_qe_prepare', 'Prepare and save periodic SCF, fixed-cell or variable-cell relaxation inputs locally with ASE. Does not submit or consume remote compute. Review the returned scientific parameters, files and resource request before calling highzyme_qe_submit with this job ID.', {
    resource_id: { type: 'string', required: true }, structure_file: { type: 'string', required: true },
    pseudopotentials: { type: 'object', additionalProperties: true, required: true, description: 'Element -> project-relative UPF file' },
    parameters: { type: 'object', additionalProperties: true, required: true, description: '{calculation: scf|relax|vc-relax, ecutwfc: Ry, ecutrho: Ry, kpoints: [kx,ky,kz], fixed_atoms?: [zero-based indices], magnetic_moments?: [per atom], system?: {...}, electrons?: {...}, ions?: {...}, cell?: {...}, control?: {...}}' },
    language: { type: 'string', enum: ['zh', 'en'] }, ...candidateParameters, ...resourcesSchema,
  }, async (args, exec) => {
    const p = await requireProject(exec);
    return prepareQE(p, args, ownerFor(p, exec.agent.session), exec.signal);
  });
  tool('highzyme_qe_submit', 'Submit an inspected, prepared QE calculation by job ID using its saved inputs and resource request. Requires explicit user authorization for this calculation. Repeated calls return the existing job without another submission.', {
    job_id: { type: 'string', required: true },
  }, async (args, exec) => submitQE(await requireProject(exec), args.job_id, exec.signal));
  tool('highzyme_qe_workflow_prepare', 'Load scientific-computing. Prepare a project JSON workflow for convergence, adsorption, formation energy, electronic structure, charge analysis, reaction free energy or NEB. No remote submission. Reuses highzyme_qe_submit/status/collect and existing project artifacts.', {
    file: { type: 'string', required: true }, resource_id: { type: 'string', required: true }, language: { type: 'string', enum: ['zh', 'en'] }, ...candidateParameters, ...resourcesSchema,
  }, async (args, exec) => { const p = await requireProject(exec); return prepareWorkflow(p, resources, args, ownerFor(p, exec.agent.session), exec.signal); });
  const testQE = async (p, resourceId, owner, language = 'en', signal) => {
    if (!p.access.compute || !p.access.network) throw new Error('Enable external computation and network access first');
    const resource = resources.get(resourceId);
    if (!resource.enabled || resource.transport !== 'ssh') throw new Error('Enable an SSH/Slurm resource first');
    const sample = fileURLToPath(new URL('../../../examples/general-research/qe-smoke/', import.meta.url));
    let folder = (owner.caseId ? p.case(owner.caseId).folder + '/' : '') + 'inputs/qe-smoke';
    const base = folder;
    for (let n = 2; await fs.access(checkedPath(p.root, folder)).then(() => true, () => false); n++) folder = base + '-' + n;
    const names = ['silicon.extxyz', 'parameters.json', 'si-pbe-rrkj.upf', 'pseudopotential-source.json'];
    for (const file of names) if (!p.permitted(folder + '/' + file, 'write')) throw new Error('Grant write access to: ' + folder);
    const url = 'https://pseudopotentials.quantum-espresso.org/upf_files/Si.pbe-rrkj.UPF';
    const response = await fetch(url, { signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(60000)]) : AbortSignal.timeout(60000) });
    if (!response.ok) throw new Error('Could not download the QE test pseudopotential: ' + response.status);
    const pseudo = Buffer.from(await response.arrayBuffer());
    await fs.mkdir(checkedPath(p.root, folder), { recursive: true });
    for (const name of names.slice(0, 2)) await fs.copyFile(path.join(sample, name), checkedPath(p.root, folder + '/' + name));
    await fs.writeFile(checkedPath(p.root, folder + '/si-pbe-rrkj.upf'), pseudo);
    await fs.writeFile(checkedPath(p.root, folder + '/pseudopotential-source.json'), JSON.stringify({ url, sha256: createHash('sha256').update(pseudo).digest('hex') }, null, 2));
    const prepared = await prepareQE(p, { resource_id: resourceId, structure_file: folder + '/silicon.extxyz',
      pseudopotentials: { Si: folder + '/si-pbe-rrkj.upf' }, parameters: JSON.parse(await fs.readFile(path.join(sample, 'parameters.json'), 'utf8')),
      ranks: 1, threads: 1, memory_mb: 1024, timeout_seconds: 300, language }, owner, signal);
    return submitQE(p, prepared.id, signal);
  };
  tool('highzyme_qe_test', 'Run the bundled two-atom silicon SCF execution test only when requested. Downloads its official QE UPF, uses one core, 1024 MiB and a five-minute limit, and saves files in the current project/case. This checks execution, not production cutoff/k-point convergence.', {
    resource_id: { type: 'string', required: true }, language: { type: 'string', enum: ['zh', 'en'] },
  }, async (args, exec) => { const p = await requireProject(exec); return testQE(p, args.resource_id, ownerFor(p, exec.agent.session), args.language, exec.signal); });
  tool('highzyme_qe_collect', 'Retrieve an ended QE calculation or scientific workflow, check required convergence and outputs, parse numeric results/structures and publish inputs, logs, tables, figures and report as one Git-versioned artifact. Failed jobs retain diagnostics.', {
    job_id: { type: 'string', required: true },
  }, async (args, exec) => collectQE(await requireProject(exec), resources, args.job_id, jobUpdate, exec.signal));
  return { prepareQE, prepareWorkflow: (p, args, owner, signal) => prepareWorkflow(p, resources, args, owner, signal), submitQE, testQE };
}

export async function collectQE(p, resources, id, jobUpdate, signal) {
  const record = (await p.jobs()).find(j => j.id === id && j.qe);
  if (!record) throw new Error('QE task not found');
  const job = await jobUpdate(p, id, 'status', signal);
  if (['queued', 'running', 'submitting', 'submission_unknown'].includes(job.status)) throw new Error('The calculation has not ended; inspect its current status');
  if (record.qe.workflow) return collectWorkflow(p, resources, record, job, signal);
  const folder = record.qe.folder, directory = checkedPath(p.root, folder);
  for (const file of ['report.md', 'result.json', 'final.extxyz', 'final.cif', 'convergence.png', 'convergence.svg']) {
    if (!p.permitted(folder + '/' + file, 'write')) throw new Error('Grant write access to: ' + folder + '/' + file);
  }
  const downloads = ['qe.out', 'stdout.log', 'stderr.log', 'submit.sh'].filter(file => job.files.includes(file));
  for (const file of downloads) {
    const rel = folder + '/' + file;
    if (!p.permitted(rel, 'write')) throw new Error('Grant write access to: ' + rel);
    await resources.download(record.resource_id, id, file, checkedPath(p.root, rel), signal);
  }
  const collected = await runPython('highzyme.compute.qe_calculation', { action: 'collect', directory, job, language: record.qe.language }, signal);
  const files = Object.fromEntries(Object.entries(collected.files).map(([key, file]) => [key, folder + '/' + file]));
  const artifact = await p.mutate(() => p.publish({ artifactId: record.artifactId, title: 'Quantum ESPRESSO · ' + collected.result.request.structure.formula,
    file: files.report, kind: 'result', sessionId: record.sessionId, caseId: record.caseId, enforceGrant: true,
    validation: record.validation, files, relatedFiles: Object.values(files), sourceReferences: record.qe.sources,
    analysis: { operation: 'quantum-espresso', outputPrefix: folder, inputs: record.qe.sources } }));
  await p.saveJob({ ...job, artifactId: artifact.id, scientific_status: collected.result.status, collection_status: 'completed', last_error: null });
  const resource = resources.get(record.resource_id);
  resource.lastCalculation = { time: Date.now(), jobId: id, converged: collected.result.status === 'converged', engine: 'quantum_espresso' };
  await resources.persist();
  return { ...collected.result, files, artifact };
}
