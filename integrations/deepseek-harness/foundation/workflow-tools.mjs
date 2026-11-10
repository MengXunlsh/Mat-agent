import fs from 'node:fs/promises';
import { candidateValidation } from './case-research.mjs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { checkedPath } from './research.mjs';
import { runPython } from './science.mjs';
import { resourceRequest } from './resource-policy.mjs';

export function workflowTitle(method, language = 'en') {
  const names = language === 'zh' ? {
    convergence: '参数收敛', adsorption: '吸附与结合能', 'formation-energy': '缺陷与位点稳定性', 'electronic-structure': '电子结构', 'charge-analysis': '电荷分析', 'reaction-energy': '反应能与自由能', neb: '反应路径与势垒',
  } : {
    convergence: 'Parameter convergence', adsorption: 'Adsorption and binding', 'formation-energy': 'Defect and site stability', 'electronic-structure': 'Electronic structure', 'charge-analysis': 'Charge analysis', 'reaction-energy': 'Reaction energy and free energy', neb: 'Reaction path and barrier',
  };
  return 'Quantum ESPRESSO · ' + names[method];
}

export async function prepareWorkflow(p, resources, args, owner, signal) {
  const validation = await candidateValidation(p, args, owner);
  if (!p.permitted(args.file)) throw new Error('Grant read access to: ' + args.file);
  const config = JSON.parse(await fs.readFile(checkedPath(p.root, args.file), 'utf8'));
  if (!Array.isArray(config.models) || !config.models.length || !config.parameters || !config.pseudopotentials) throw new Error('Select a scientific-computing configuration with models, parameters and pseudopotentials');
  const sources = [...new Set([args.file, ...config.models.map(m => m.structure_file), ...Object.values(config.pseudopotentials)])];
  for (const file of sources) { checkedPath(p.root, file); if (!p.permitted(file)) throw new Error('Grant read access to: ' + file); }
  const resource = resources.get(args.resource_id);
  if (resource.transport !== 'ssh') throw new Error('Select an SSH/Slurm resource for QE workflows');
  const request = resourceRequest(resource, args);
  let folder = path.posix.dirname(await p.artifactPath({ title: 'Scientific calculation', fileStem: 'calculation-report', ...owner })) + '/qe-workflow';
  const base = folder;
  for (let n = 2; await fs.access(checkedPath(p.root, folder)).then(() => true, () => false); n++) folder = base + '-' + n;
  if (!p.permitted(folder, 'write')) throw new Error('Grant write access to the calculation folder: ' + folder);
  const programs = { pw: resource.qe_command || resource.probe?.programs?.quantum_espresso || 'pw.x', ...resource.program_commands };
  const value = await runPython('highzyme.compute.qe_workflows', { action: 'prepare', root: p.root, directory: checkedPath(p.root, folder), config, programs }, signal);
  const row = { id: 'job-' + randomUUID().replaceAll('-', ''), status: 'prepared', created_at: Date.now() / 1000, ...owner,
    validation, label: workflowTitle(config.method, args.language), type: 'compute', capability: 'quantum_espresso', resource_id: resource.id, resources: request,
    qe: { workflow: true, folder, sources, language: args.language || 'en', method: config.method, summary: { models: value.manifest.models, requests: value.manifest.requests, analysis: value.manifest.analysis }, stages: value.manifest.stages.map(s => ({ id: s.id, program: s.program })),
      required_programs: value.required_programs, inputs: value.input_files.map(f => ({ file: folder + '/' + f.target, target: f.target, sha256: f.sha256 })) } };
  await p.saveJob(row); return row;
}

export async function collectWorkflow(p, resources, record, job, signal) {
  const folder = record.qe.folder, directory = checkedPath(p.root, folder);
  if (!p.permitted(folder, 'write')) throw new Error('Grant write access to: ' + folder);
  const stages = record.qe.stages.map(s => s.id + '/');
  const outputs = job.files.filter(file => ['workflow-status.json', 'stdout.log', 'stderr.log', 'submit.sh'].includes(file) || stages.some(s => file.startsWith(s)) &&
    (/\.(out|dat|gnu|cube|xyz|extxyz|int|path)$/.test(file) || /(?:pdos|ACF\.dat)/.test(path.posix.basename(file))) && !file.includes('/pseudo/'));
  if (outputs.length) await resources.downloadMany(record.resource_id, job.id, outputs, directory, signal);
  const collected = await runPython('highzyme.compute.qe_workflows', { action: 'collect', directory, job, language: record.qe.language }, signal);
  const files = Object.fromEntries(Object.entries(collected.files).map(([key, file]) => [key, folder + '/' + file]));
  const related = [...new Set([...Object.values(files), ...record.qe.inputs.map(f => f.file), ...outputs.map(f => folder + '/' + f)])];
  const title = workflowTitle(record.qe.method, record.qe.language) + (collected.result.status === 'completed' ? '' : record.qe.language === 'zh' ? ' · 未完成' : ' · Incomplete');
  const artifact = await p.mutate(() => p.publish({ artifactId: record.artifactId, title, file: files.report, kind: 'result',
    sessionId: record.sessionId, caseId: record.caseId, enforceGrant: true, validation: record.validation, files, relatedFiles: related, sourceReferences: record.qe.sources,
    analysis: { operation: 'quantum-espresso-workflow', method: record.qe.method, outputPrefix: folder, inputs: record.qe.sources } }));
  await p.saveJob({ ...job, artifactId: artifact.id, scientific_status: collected.result.status, collection_status: 'completed', last_error: null });
  resources.get(record.resource_id).lastCalculation = { time: Date.now(), jobId: job.id, converged: collected.result.status === 'completed', engine: 'quantum_espresso', method: record.qe.method };
  await resources.persist();
  return { ...collected.result, files, artifact };
}
