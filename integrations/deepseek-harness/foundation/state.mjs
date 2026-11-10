import { promises as fs } from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { runPython } from './science.mjs';
import { resourcePolicy, resourceRequest } from './resource-policy.mjs';

export function inside(root, name) {
  if (!name || name.includes('\\') || name.includes(':') || name.split('/').some(p => !p || p === '..' || p === '.')) throw new Error('Invalid project path');
  const result = path.resolve(root, name);
  if (!result.startsWith(path.resolve(root) + path.sep)) throw new Error('Path outside project');
  return result;
}

export async function writeJson(file, value) {
  await fs.mkdir(path.dirname(file), { recursive: true });
  const temp = file + '.' + randomUUID() + '.tmp';
  await fs.writeFile(temp, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
  await fs.rename(temp, file);
}

export async function readJson(file, fallback) {
  try { return JSON.parse(await fs.readFile(file, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return fallback; throw error; }
}

/** Capability state is invalidated by restart/configuration change; enabling always probes again. */
export class ComputeResources {
  constructor(home, credentials) { this.file = path.join(home, 'compute.json'); this.home = home; this.credentials = credentials; this.rows = []; this.probes = new Map(); }
  async load() { this.rows = (await readJson(this.file, [])).map(r => ({ ...r, enabled: false })); await this.persist(); }
  async persist() { await writeJson(this.file, this.rows); }
  list() { return this.rows.map(r => ({ ...r, probe: this.probes.get(r.id) || null })); }
  get(id) { const r = this.rows.find(r => r.id === id); if (!r) throw new Error('Resource not found'); return r; }
  async configure(input) {
    const id = input.id || randomUUID();
    if (!/^[a-zA-Z0-9_-]{1,80}$/.test(id)) throw new Error('Invalid resource ID');
    let row;
    if (input.transport === 'ssh') {
      const profile = await runPython('highzyme.compute.ssh_slurm', { action: 'validate', profile: input });
      row = { ...profile, id, name: String(input.name || input.host).slice(0, 120), transport: 'ssh', scheduler: 'slurm', enabled: false };
    } else {
      const url = new URL(input.url);
      if (url.username || url.password || url.search || url.hash || (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)))) throw new Error('Use HTTPS or a loopback SSH tunnel URL');
      const ref = 'HIGHZYME_COMPUTE_' + id.replaceAll('-', '_').toUpperCase();
      if (input.token) await this.credentials.set(ref, input.token);
      if (!(await this.credentials.resolve(ref))) throw new Error('Enter the compute service token');
      row = { id, name: String(input.name || 'Compute').slice(0, 120), transport: 'http', url: url.toString().replace(/\/$/, ''), credentialRef: ref, enabled: false };
    }
    Object.assign(row, resourcePolicy(input));
    const previous = this.rows.find(r => r.id === id);
    if (input.setupSessionId || previous?.setupSessionId) row.setupSessionId = input.setupSessionId || previous.setupSessionId;
    if (previous?.lastCalculation) row.lastCalculation = previous.lastCalculation;
    this.rows = this.rows.filter(r => r.id !== id).concat(row); this.probes.delete(id); await this.persist(); return row;
  }
  async request(id, route, body, signal) {
    if (this.get(id).transport === 'ssh') {
      const match = route.match(/^\/jobs\/(job-[a-f0-9]{32})(\/cancel)?$/);
      if (route === '/health') return this.ssh(id, { action: 'probe' }, signal);
      if (route === '/jobs') return this.ssh(id, { action: 'submit', task: body }, signal);
      if (match) return this.ssh(id, { action: match[2] ? 'cancel' : 'status', job_id: match[1] }, signal);
      throw new Error('Unknown SSH compute operation');
    }
    const r = this.get(id), credential = await this.credentials.resolve(r.credentialRef);
    if (!credential) throw new Error('Compute credential missing');
    const response = await fetch(r.url + route, { method: body === undefined ? 'GET' : 'POST', redirect: 'error', headers: { Authorization: 'Bearer ' + credential.value, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20000)]) : AbortSignal.timeout(20000) });
    const value = await response.json(); if (!response.ok) throw new Error(value.error || `Compute service ${response.status}`); return value;
  }
  async probe(id) {
    try {
      const health = await this.request(id, '/health');
      if (health.protocol !== 'highzyme-compute-v1' || !Array.isArray(health.capabilities)) throw new Error('Not a compatible compute service');
      const result = { ...health, checkedAt: Date.now(), ready: health.ready !== false }; this.probes.set(id, result);
      if (!result.ready) { this.get(id).enabled = false; await this.persist(); }
      return result;
    } catch (error) { this.get(id).enabled = false; this.probes.set(id, { ready: false, error: error.message }); await this.persist(); throw error; }
  }
  async enable(id, enabled) { const r = this.get(id); if (enabled && !(await this.probe(id)).ready) throw new Error('Scheduler or writable work directory is unavailable'); r.enabled = !!enabled; await this.persist(); return r; }
  async remove(id) { const r = this.get(id); if (r.credentialRef) await this.credentials.unset(r.credentialRef); this.rows = this.rows.filter(v => v.id !== id); this.probes.delete(id); await this.persist(); }
  ssh(id, request, signal) { return runPython('highzyme.compute.ssh_slurm', { ...request, profile: this.get(id), state: path.join(this.home, 'compute-jobs', id) }, signal); }
  async download(id, jobId, file, destination, signal) {
    if (this.get(id).transport === 'ssh') return this.ssh(id, { action: 'download', job_id: jobId, file, destination }, signal);
    const result = await this.request(id, '/jobs/' + jobId + '/file?path=' + encodeURIComponent(file), undefined, signal);
    await fs.mkdir(path.dirname(destination), { recursive: true }); await fs.writeFile(destination, Buffer.from(result.data, 'base64'));
    return { file: destination, bytes: result.bytes };
  }
  downloadMany(id, jobId, files, destination, signal) {
    return this.ssh(id, { action: 'download_many', job_id: jobId, files, destination }, signal);
  }
  async submit(id, task, signal) {
    if (!this.get(id).enabled) throw new Error('COMPUTE_DISABLED: enable a connected resource in Settings');
    const request = { ...task, ...resourceRequest(this.get(id), task) };
    if (this.get(id).transport === 'ssh') return this.request(id, '/jobs', request, signal);
    const health = await this.probe(id);
    if (!this.get(id).enabled) throw new Error('COMPUTE_DISABLED: resource was disabled during validation');
    if (!health.capabilities.includes(task.capability)) throw new Error('Resource does not provide ' + task.capability);
    return this.request(id, '/jobs', this.get(id).transport === 'ssh' ? request : { ...request, cores: request.threads }, signal);
  }
}
