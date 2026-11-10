import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { ResearchProject, git, deniedTool } from './research.mjs';
import { fitProjectKinetics, replotProjectKinetics } from './kinetics.mjs';
import { resultFileAction } from './project-science.mjs';
import { registerArtifactTools } from './artifact-tools.mjs';

const runtime = createRequire(new URL('../web-runtime/package.json', import.meta.url));
const { defineTool } = await import(pathToFileURL(runtime.resolve('@deepseek-ai/dsh-tools')).href);

async function fixture(callback) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-bundle-'));
  try { await callback(await new ResearchProject({ id: 'project', path: root }).load()); }
  finally { await fs.rm(root, { recursive: true, force: true }); }
}

test('independent datasets and repeated-input branches stay separate; explicit revision and replot keep their artifact', () => fixture(async p => {
  const owner = { sessionId: 'analysis-chat', caseId: null };
  const csv = (km, vmax) => 's,v,alternate\n' + [.02, .05, .1, .2, .4, .8, 1.6].map(s => `${s},${vmax*s/(km+s)},${4*s/(.8+s)}`).join('\n') + '\n';
  await fs.writeFile(path.join(p.root, 'first.csv'), csv(.3, 2.4));
  await fs.writeFile(path.join(p.root, 'second.csv'), csv(.8, 4));
  const args = { file: 'first.csv', concentration_column: 's', rate_column: 'v', concentration_unit: 'mM', rate_unit: 'uM/s' };
  const first = await fitProjectKinetics(p, args, owner);
  const firstJSON = await fs.readFile(path.join(p.root, first.files.result), 'utf8');
  const byRole = await p.readArtifact(first.artifact.id, undefined, true, { file: 'result', maxChars: 100 });
  const byName = await p.readArtifact(first.artifact.id, undefined, true, { file: path.posix.basename(first.files.result), maxChars: 100 });
  assert.equal(byRole.file, first.files.result);
  assert.equal(byName.file, first.files.result);
  assert.equal(byName.revision, byRole.revision);
  const second = await fitProjectKinetics(p, { ...args, file: 'second.csv' }, owner);
  assert.notEqual(first.artifact.id, second.artifact.id);
  assert.notEqual(first.files.report, second.files.report);
  assert.equal(await fs.readFile(path.join(p.root, first.files.result), 'utf8'), firstJSON);
  const branch = await fitProjectKinetics(p, { ...args, new_analysis: true }, owner);
  assert.notEqual(branch.artifact.id, first.artifact.id);
  assert.notEqual(branch.files.result, first.files.result);
  const revised = await fitProjectKinetics(p, { ...args, rate_column: 'alternate', artifact_id: first.artifact.id }, owner);
  assert.equal(revised.artifact.id, first.artifact.id);
  assert.equal(revised.files.report, first.files.report);
  assert.ok(Math.abs(revised.fit.km - .8) < 1e-7);
  assert.equal(revised.fit.concentration, undefined);
  const numeric = await fs.readFile(path.join(p.root, revised.files.result), 'utf8');
  const count = p.data.artifacts.length;
  const plot = await replotProjectKinetics(p, { file: revised.files.result, labels: ['Revised series'] }, owner);
  assert.equal(plot.artifact.id, first.artifact.id);
  assert.equal(plot.artifact.file, first.files.report);
  assert.equal(p.data.artifacts.length, count);
  assert.equal(plot.artifact.files.result, revised.files.result);
  assert.equal(await fs.readFile(path.join(p.root, revised.files.result), 'utf8'), numeric);
  assert.equal(await resultFileAction(p, revised.files.result), 'replotRates');
  await assert.rejects(fitProjectKinetics(p, { ...args, artifact_id: first.artifact.id, new_analysis: true }, owner), /revision or independent/);
}));

test('custom bundles preserve members on edits and pin text and binary together, including an auxiliary-only revision', () => fixture(async p => {
  const c = await p.createCase('Use an earlier analysis');
  await p.attachSession(c.id, 'case-chat');
  const tools = new Map();
  registerArtifactTools({ tool(name, description, parameters, execute) {
    defineTool({ name, description, parameters, execute, output: { schema: { type: 'object', additionalProperties: true }, render: () => [] } });
    tools.set(name, execute);
  }, requireProject: async () => p, ownerFor: () => ({ sessionId: 'analysis-chat', caseId: null }), caseFor: (project, session) => project.caseFor(session) });
  await fs.writeFile(path.join(p.root, 'data.csv'), 'sample,value\na,1\n');
  await fs.writeFile(path.join(p.root, 'analysis.py'), 'print(1)\n');
  const image = Buffer.from([0, 1, 254, 255, 0, 3]);
  await fs.writeFile(path.join(p.root, 'image.bin'), image);
  const a = await tools.get('highzyme_artifact_save')({ title: 'Custom analysis', file: 'report.md', content: '# Report\nOriginal result.', kind: 'result',
    related_files: ['data.csv', 'analysis.py', 'image.bin'], files: { report: 'report.md', data: 'data.csv', code: 'analysis.py', image: 'image.bin' },
    source_references: ['input.csv SHA-256: retained-source'] }, { agent: { session: { id: 'analysis-chat' } } });
  const ref = await p.reference(c.id, a.id);
  const originalRevision = ref.revision;
  await fs.writeFile(path.join(p.root, 'data.csv'), 'sample,value\na,2\n');
  await fs.writeFile(path.join(p.root, 'image.bin'), Buffer.from([0, 5, 6]));
  await p.publish({ artifactId: a.id, enforceGrant: true });
  assert.match((await tools.get('highzyme_artifact_read')({ artifact_id: a.id, file: 'data.csv' }, { agent: { session: { id: 'case-chat' } } })).content, /a,1/);
  const reopened = await new ResearchProject({ id: p.id, path: p.root }).load();
  const current = reopened.data.artifacts.find(row => row.id === a.id);
  assert.notEqual(current.revision, originalRevision);
  assert.notEqual(current.revision, await git(p.root, ['log', '-1', '--format=%H', '--', 'report.md']));
  assert.equal(current.relatedFiles.length, 4);
  assert.equal(current.sourceReferences[0], 'input.csv SHA-256: retained-source');
  assert.equal(current.sessionId, 'analysis-chat');
  assert.match((await reopened.readArtifact(a.id, undefined, true, { file: 'data.csv' })).content, /a,2/);
  const oldData = await reopened.readArtifact(a.id, c.id, true, { file: 'data.csv', maxChars: 8 });
  assert.equal(oldData.content, 'sample,v'); assert.equal(oldData.nextOffset, 8);
  assert.match((await reopened.readArtifact(a.id, c.id, true, { file: 'data.csv', offset: 8, maxChars: 64 })).content, /a,1/);
  const exclude = path.resolve(p.root, await git(p.root, ['rev-parse', '--git-path', 'info/exclude']));
  await fs.writeFile(exclude, (await fs.readFile(exclude, 'utf8')).replace('.highzyme/reference-files/\n', ''));
  const oldImage = await reopened.readArtifact(a.id, c.id, true, { file: 'image.bin', materialize: true });
  assert.equal(oldImage.binary, true); assert.equal(oldImage.content, undefined);
  assert.deepEqual(await fs.readFile(path.join(p.root, oldImage.localFile)), image);
  assert.equal(oldImage.revision, originalRevision);
  assert.deepEqual(oldImage.files, ref.files);
  assert.doesNotMatch(await git(p.root, ['status', '--porcelain']), /reference-files/);
  await assert.rejects(reopened.readArtifact(a.id, c.id, true, { file: 'input.csv' }), /from this artifact version/);
  await assert.rejects(reopened.readArtifact(a.id, c.id, true, { maxChars: 0 }), /text limit/);
  await reopened.setAccess({ content: 'selected', read: ['report.md'], write: [] });
  assert.equal(reopened.permitted(oldImage.localFile), false);
  await assert.rejects(reopened.readArtifact(a.id, c.id, true, { file: 'data.csv' }), /Grant Agent access/);
  await reopened.setAccess({ content: 'selected', read: ['report.md', 'image.bin'], write: ['.'] });
  assert.equal(reopened.permitted(oldImage.localFile), true);
  assert.equal(reopened.permitted(oldImage.localFile, 'write'), false);
  assert.equal(deniedTool(reopened, { name: 'read_image', arguments: { path: path.join(p.root, oldImage.localFile) } }, p.root), undefined);
  await assert.rejects(reopened.publish({ artifactId: a.id, content: '# Denied edit', enforceGrant: true }), /Grant access/);
  assert.equal(await fs.readFile(path.join(p.root, 'report.md'), 'utf8'), '# Report\nOriginal result.');
  const legacy = reopened.case(c.id).references[0]; delete legacy.relatedFiles; delete legacy.files;
  assert.equal((await reopened.readArtifact(a.id, c.id, false, { metadataOnly: true })).files.code, 'analysis.py');
}));

test('file shortcuts use actual saved result types, not a result filename alone', () => fixture(async p => {
  for (const [name, data, expected] of [
    ['recipe-result.json', { schema: 'highzyme.calculation.v1', calculation: 'formulation', plot: null }, null],
    ['image-result.json', { schema: 'highzyme.calculation.v1', calculation: 'colorimetry', plot: null }, null],
    ['signal-result.json', { schema: 'highzyme.calculation.v1', calculation: 'signal', plot: { series: [{ x: [1], y: [2] }] } }, 'replotRates'],
    ['other-result.json', { arbitrary: true }, null],
  ]) {
    await fs.writeFile(path.join(p.root, name), JSON.stringify(data));
    assert.equal(await resultFileAction(p, name), expected);
  }
  await p.setAccess({ content: 'selected', read: [], write: ['.'] });
  assert.equal(await resultFileAction(p, 'signal-result.json'), null);
  assert.match(deniedTool(p, { name: 'highzyme_formulation', arguments: { new_analysis: true } }, p.root, 'read-only'), /read-only/);
}));
