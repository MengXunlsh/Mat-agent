import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { existsSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { DatasetService, saveDatasetRecord, registerDatasetTools } from './dataset.mjs';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { ResearchProject, deniedTool } from './research.mjs';
import { artifactVisual } from './result-views.mjs';
import { science } from './science.mjs';
import { registerArtifactTools } from './artifact-tools.mjs';

const registry = process.env.HIGHZYME_DATASET_REGISTRY || ['nanozyme-database', 'Highzyme_Database'].map(folder => fileURLToPath(new URL('../../../' + folder + '/database/database_registry.json', import.meta.url))).find(existsSync);
const runtime = createRequire(new URL('../web-runtime/package.json', import.meta.url));
const { defineTool } = await import(pathToFileURL(runtime.resolve('@deepseek-ai/dsh-tools')).href);

test('native Harness compiles the full dataset tool catalog', () => {
  const names = [];
  registerDatasetTools({ tool(name, description, parameters, execute) {
    defineTool({ name, description, parameters, execute, output: { schema: { type: 'object', additionalProperties: true }, render: () => [] } }); names.push(name);
  } });
  assert.equal(names.length, 6);
});

test('scientific operation errors preserve the actionable message', async () => {
  await assert.rejects(science({ action: 'identity', formula: 'not-a-formula' }), /formula|element|token|character|syntax/i);
});

test('dataset save obeys native read-only mode', () => {
  assert.match(deniedTool({ access: {} }, { name: 'highzyme_dataset_save', args: {} }, '', 'read-only'), /read-only/);
});

test('cached dataset access rejects a source changed after verification', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-dataset-integrity-'));
  const dataset = new DatasetService(root);
  try {
    const material = { schema: 'highzyme.material.reported.parallel.v2', material_id: 'M1', material_name: 'Fe3O4', aliases: [],
      sources: {}, default_sources: [], material_features: {}, application_information: {}, variants: [], material_information_records: [] };
    const assets = { data: 'materials.jsonl', trace: 'provenance.jsonl', mapping: 'origins.jsonl' }, hashes = {};
    for (const [key, name] of Object.entries(assets)) {
      const text = key === 'data' ? JSON.stringify(material) + '\n' : '';
      await fs.writeFile(path.join(root, name), text); hashes[key] = createHash('sha256').update(text).digest('hex');
    }
    const registryFile = path.join(root, 'database_registry.json');
    await fs.writeFile(registryFile, JSON.stringify({ active_release: 'test', path_base: 'directory containing this registry',
      releases: [{ release_id: 'test', layout: 'integrated', schema: material.schema, ...assets, expected_sha256: hashes }] }));
    await dataset.configure(registryFile);
    await fs.appendFile(path.join(root, assets.data), '\n');
    await assert.rejects(dataset.request('search', { limit: 5 }), /hash|changed|mismatch/i);
  } finally { dataset.dispose(); await fs.rm(root, { recursive: true, force: true }); }
});

test('real packaged records paginate, retain provenance, publish and preview using project Git', { skip: !registry || !existsSync(registry) }, async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-dataset-'));
  const dataset = new DatasetService(path.join(root, 'home'));
  try {
    await dataset.load();
    const info = await dataset.configure(registry);
    assert.equal(info.catalog.datasets[0].materials, 1346);
    assert.equal(info.catalog.datasets[0].measurement_records, 4887);
    const filters = await dataset.request('catalog', { section: 'filters' });
    assert.ok(filters.datasets[0].facets.applications.length);
    const app = filters.datasets[0].facets.applications[0];
    const appHits = await dataset.request('search', { application_major: app.major_category, limit: 2 });
    assert.ok(appHits.matching_assay_scopes > 0);
    const first = await dataset.request('search', { material: 'Fe3O4', record_kind: 'kinetic', limit: 5 });
    const next = await dataset.request('search', { material: 'Fe3O4', record_kind: 'kinetic', limit: 5, offset: first.page.next_offset });
    assert.equal(first.hits.length, 5); assert.equal(next.hits.length, 5);
    assert.equal(new Set([...first.hits, ...next.hits].map(h => h.selection_id)).size, 10);
    const material = await dataset.request('material', { material_id: first.hits[0].material_id, limit: 3 });
    assert.equal(material.groups[0].hits.length, 3);
    assert.equal(material.groups[0].record_page.next_offset, 3);
    if (dataset.analysisRegistry) {
      const neighbors = await dataset.request('space', { options: { operation: 'neighbors', material_id: first.hits[0].material_id, limit: 2, independent_only: true } });
      assert.equal(neighbors.source.database_sha256, first.hits[0].data_sha256);
      assert.ok(neighbors.data.neighbors.every(n => n.source_independent));
      const applications = await dataset.request('space', { options: { operation: 'applications', material_id: first.hits[0].material_id, limit: 2 } });
      assert.ok(applications.data.candidates.length <= 2);
    }
    const read = await dataset.request('read', { selection_id: first.hits[0].selection_id });
    assert.equal(read.read, true); assert.equal(read.source_document_read, false);
    assert.equal(read.coverage.truncated, false);
    assert.ok(read.observations.some(o => o.source?.length));
    await fs.mkdir(path.join(root, 'project'));
    const project = await new ResearchProject({ id: 'project', path: path.join(root, 'project') }).load();
    const artifact = await saveDatasetRecord(project, dataset, first.hits[0].selection_id, { sessionId: 'discussion' });
    assert.ok(artifact.revision); assert.match(artifact.file, /^artifacts\/.+\.json$/);
    const visual = await artifactVisual(project, { artifactId: artifact.id });
    assert.equal(visual.kind, 'dataset'); assert.ok(visual.tables[0].rows.length);
    const other = await saveDatasetRecord(project, dataset, first.hits[1].selection_id, { sessionId: 'discussion' });
    const otherData = JSON.parse(await fs.readFile(path.join(project.root, other.file), 'utf8'));
    const comparison = await science({ action: 'compare_evidence', root: project.root, output_prefix: path.join(project.root, 'comparison'), selections: [
      { file: path.join(project.root, artifact.file), source_label: artifact.file, assay_ids: [read.selection.assay_id] },
      { file: path.join(project.root, other.file), source_label: other.file, assay_ids: [otherData.selection.assay_id] },
    ] });
    assert.equal(comparison.series_count, 2);
    const revised = await saveDatasetRecord(project, dataset, first.hits[0].selection_id, { sessionId: 'discussion' });
    assert.equal(revised.id, artifact.id); assert.equal(project.data.artifacts.length, 2);
    const coHits = await dataset.request('search', { material: 'Co0.5-Fe3O4', record_kind: 'kinetic', limit: 1 });
    const co = await saveDatasetRecord(project, dataset, coHits.hits[0].selection_id, { sessionId: 'discussion' });
    const stored = JSON.parse(await fs.readFile(path.join(project.root, co.file), 'utf8'));
    assert.equal(stored.coverage.truncated, false);
    assert.equal(stored.observations.length, stored.coverage.observations_selected);
    assert.ok(stored.observations.some(o => o.field === 'reported_results.km'));
    assert.ok(stored.observations.some(o => o.field === 'reported_results.vmax'));
    assert.ok(JSON.stringify(co.record).length < JSON.stringify(stored).length / 2);
    const full = await dataset.request('read', { selection_id: coHits.hits[0].selection_id, detail: 'full' });
    assert.deepEqual(stored.observations, full.observations);
    const tools = new Map();
    const c = await project.createCase('Pinned dataset review');
    const reference = await project.reference(c.id, co.id);
    registerArtifactTools({ tool: (name, _description, _parameters, execute) => tools.set(name, execute), requireProject: async () => project, ownerFor: () => ({ sessionId: 'discussion' }), caseFor: () => c });
    await fs.writeFile(path.join(project.root, co.file), '{"changedWorkingFile":true}');
    const pinned = await tools.get('highzyme_artifact_read')({ artifact_id: co.id, view: 'dataset', fields: ['reported_results.km'], detail: 'full' }, { agent: { session: { id: 'discussion' } } });
    assert.equal(pinned.id, co.id);
    assert.equal(pinned.revision, reference.revision);
    assert.deepEqual(JSON.parse(JSON.stringify(pinned)), pinned);
    assert.equal(pinned.record.observations[0].field, 'reported_results.km');
    assert.ok(pinned.record.observations[0].trace);
    assert.equal(pinned.record.coverage.observations_returned, pinned.record.observations.length);
    await assert.rejects(dataset.request('search', { limit: 31 }), /limit/);
    assert.equal((await dataset.request('search', { query: 'missing-material-xyz123', limit: 5 })).hits.length, 0);
    const reloaded = new DatasetService(path.join(root, 'home'));
    await reloaded.load(); assert.equal(reloaded.registry, registry); reloaded.dispose();
  } finally { dataset.dispose(); await fs.rm(root, { recursive: true, force: true }); }
});
