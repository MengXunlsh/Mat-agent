import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { scientificRuntime } from './science.mjs';
import { readJson, writeJson } from './state.mjs';
import { englishStem } from './research.mjs';

const root = fileURLToPath(new URL('../../../', import.meta.url));

export class DatasetService {
  constructor(home) {
    this.file = path.join(home, 'dataset.json');
    this.pending = [];
    this.requests = new Map();
  }
  async load() {
    const bundled = ['nanozyme-database', 'Highzyme_Database'].map(folder => path.join(root, folder, 'database/database_registry.json')).find(existsSync);
    const saved = await readJson(this.file, {});
    this.registry = saved.registry ?? process.env.HIGHZYME_DATASET_REGISTRY ?? bundled ?? '';
    const analysis = path.join(root, 'protocol/material-space-registry.json');
    this.analysisRegistry = saved.analysisRegistry ?? process.env.HIGHZYME_MATERIAL_SPACE_REGISTRY ?? (existsSync(analysis) ? analysis : '');
  }
  dispose() {
    this.child?.kill();
    this.child = null;
    for (const task of this.pending.splice(0)) task.reject(new Error('Dataset connection closed; search again'));
  }
  request(action, options = {}, registry = this.registry) {
    if (!registry) return Promise.reject(new Error('Connect a nanozyme dataset in Settings first'));
    const key = JSON.stringify([action, options, registry]);
    if (this.requests.has(key)) return this.requests.get(key);
    if (!this.child) {
      const child = spawn(scientificRuntime.python, ['-B', '-m', 'highzyme.dataset_runtime'], {
        cwd: root, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONPATH: path.join(root, 'src'), PYTHONIOENCODING: 'utf-8' },
      });
      this.child = child;
      let error = '';
      child.stderr.on('data', chunk => { error = (error + chunk).slice(-2000); });
      createInterface({ input: child.stdout }).on('line', line => {
        const task = this.pending.shift(); if (!task) return;
        try { const value = JSON.parse(line); value.error ? task.reject(new Error(value.error)) : task.resolve(value.result); }
        catch (error) { task.reject(error); }
      });
      const failed = () => {
        if (this.child !== child) return;
        this.child = null;
        for (const task of this.pending.splice(0)) task.reject(new Error(error || 'Dataset reader stopped; retry the search'));
      };
      child.on('error', failed); child.on('close', failed);
    }
    const result = new Promise((resolve, reject) => {
      this.pending.push({ resolve, reject });
      this.child.stdin.write(JSON.stringify({ ...options, ...(action === 'space' ? { analysis_registry: options.analysis_registry ?? this.analysisRegistry } : {}), action, registry }) + '\n');
    }).finally(() => this.requests.delete(key));
    this.requests.set(key, result); return result;
  }
  async configure(registry, analysisRegistry = this.analysisRegistry) {
    const selected = path.resolve(registry);
    const catalog = await this.request('catalog', {}, selected);
    const selectedAnalysis = analysisRegistry ? path.resolve(analysisRegistry) : '';
    if (selectedAnalysis) await this.request('space', { analysis_registry: selectedAnalysis, options: { operation: 'catalog' } }, selected);
    this.registry = selected;
    this.analysisRegistry = selectedAnalysis;
    await writeJson(this.file, { registry: selected, analysisRegistry: selectedAnalysis });
    return { registry: selected, catalog };
  }
}

export async function saveDatasetRecord(project, dataset, selectionId, owner, title) {
  const record = await dataset.request('read', { selection_id: selectionId, detail: 'full' });
  record.schema = 'highzyme.dataset-record.v1';
  const selection = record.selection;
  title ||= selection.material_name || 'Nanozyme record';
  const artifact = await project.mutate(async () => {
    const stem = 'nanozyme-' + englishStem(selection.material_name).slice(0, 64).replace(/-$/, '') + '-' + selection.selection_id.slice(-8);
    const file = (await project.artifactPath({ ...owner, title, kind: 'source', fileStem: stem })).replace(/\.md$/, '.json');
    return project.publish({
    title, kind: 'source',
    content: JSON.stringify(record, null, 2) + '\n', ...owner, enforceGrant: true,
    sourceReferences: [selection.release_id, selection.material_id, selection.version_id, selection.record_id].filter(Boolean),
    file, files: { result: file },
    });
  });
  const values = await dataset.request('read', { selection_id: selectionId });
  return { ...artifact, record: values };
}

export function registerDatasetTools({ tool, requireProject, ownerFor, dataset }) {
  tool('highzyme_dataset_catalog', 'Inspect the connected database counts, available filters, application categories or field definitions before constructing a query. Counts describe reported records, not validated comparable samples.', {
    section: { type: 'string', enum: ['overview', 'filters', 'fields'] },
  }, async (args, exec) => { await requireProject(exec); return dataset.request('catalog', { section: 'overview', ...args }); });
  tool('highzyme_dataset_material', 'List one material and a bounded page of its sample/assay records with original identities and sources. Read returned selections for numerical evidence.', {
    material_id: { type: 'string', required: true }, limit: { type: 'integer' }, offset: { type: 'integer' },
  }, async (args, exec) => { await requireProject(exec); return dataset.request('material', args); });
  tool('highzyme_material_space', 'Use a connected, hash-bound analysis resource for reported material profiles, source-independent neighbors or application-transfer candidates. Similarity is a descriptor score, not a performance prediction. A missing database use does not establish novelty.', {
    operation: { type: 'string', enum: ['catalog', 'profile', 'neighbors', 'applications'], required: true },
    material_id: { type: 'string' }, query: { type: 'string' }, view: { type: 'string', enum: ['structure', 'function'] },
    limit: { type: 'integer' }, independent_only: { type: 'boolean' }, target: { type: 'string' },
  }, async (args, exec) => { await requireProject(exec); return dataset.request('space', { options: args }); });
  tool('highzyme_dataset_search', 'Search the connected structured nanozyme dataset. Returns bounded discovery metadata, not a paper reading. Use highzyme_dataset_read for record-level observations, units and source locations. Load nanozyme-dataset for filters.', {
    query: { type: 'string' }, activity: { type: 'string' }, substrate: { type: 'string' }, material: { type: 'string' },
    ph: { type: 'string' }, source_doi: { type: 'string' }, record_kind: { type: 'string', enum: ['all', 'measurement', 'kinetic', 'unpaired_information'] },
    material_class: { type: 'string' }, application_major: { type: 'string' }, application_subcategory: { type: 'string' }, application_direction: { type: 'string' },
    version: { type: 'string' }, assay: { type: 'string' }, reactant: { type: 'string' }, temperature_min: { type: 'number' }, temperature_max: { type: 'number' },
    source_dataset: { type: 'string', enum: ['文献抽取', '外部整合'] },
    required_fields: { type: 'array', items: { type: 'string', enum: ['km', 'vmax', 'catalyst_concentration'] } },
    limit: { type: 'integer' }, offset: { type: 'integer' },
  }, async (args, exec) => { await requireProject(exec); return dataset.request('search', { limit: 5, ...args }); });
  tool('highzyme_dataset_read', 'Read every selected observation with raw units, conditions, source URLs and locators. Default values detail omits verbose lineage; use detail=full with specific fields for original quotes. This reads a dataset, not a paper.', {
    selection_id: { type: 'string', required: true },
    fields: { type: 'array', items: { type: 'string' }, description: 'Optional group.field names from available_fields, or group names; omitting reads all fields' },
    detail: { type: 'string', enum: ['values', 'full'] },
  }, async (args, exec) => { await requireProject(exec); return dataset.request('read', args); });
  tool('highzyme_dataset_save', 'Read and save the complete selected dataset record, all observations and provenance, as a source artifact. Returns its paths and concise observations, so a separate read is unnecessary unless detailed quotes are needed. Uses project permissions and Git; the dataset is unchanged.', {
    selection_id: { type: 'string', required: true }, title: { type: 'string' },
  }, async (args, exec) => { const p = await requireProject(exec); return saveDatasetRecord(p, dataset, args.selection_id, ownerFor(p, exec.agent.session), args.title); });
}
