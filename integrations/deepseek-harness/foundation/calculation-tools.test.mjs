import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { fileURLToPath } from 'node:url';
import { ResearchProject, deniedTool, git } from './research.mjs';
import { registerCalculationTools } from './calculation-tools.mjs';
import { registerDocumentTools } from './document-tools.mjs';
import { science } from './science.mjs';

const runtime = createRequire(new URL('../web-runtime/package.json', import.meta.url));
const { defineTool } = await import(pathToFileURL(runtime.resolve('@deepseek-ai/dsh-tools')).href);

test('native tool definitions execute calibration and preserve project/case files, grants and Git', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-calculation-'));
  try {
    const p = await new ResearchProject({ id: 'test', path: root }).load();
    const c = await p.createCase('Calibration'); await p.attachSession(c.id, 'session');
    const owner = { sessionId: 'session', caseId: c.id };
    const tools = new Map();
    const setup = { tool(name, description, parameters, execute) {
      defineTool({ name, description, parameters, execute, output: { schema: { type: 'object', additionalProperties: true }, render: () => [] } });
      tools.set(name, execute);
    }, requireProject: async () => p, ownerFor: () => owner };
    registerCalculationTools(setup); registerDocumentTools(setup);
    await fs.writeFile(path.join(root, 'calibration.csv'), 'x,y\n0,1\n1,3\n2,5\n3,7\n4,9\n');
    const args = { file: 'calibration.csv', operation: 'fit_calibration', columns: { x: 'x', y: 'y' },
      parameters: { x_unit: 'uM', y_unit: 'a.u.' }, language: 'zh' };
    const exec = { agent: { session: { id: 'session' } } };
    const result = await tools.get('highzyme_analyze_signal')(args, exec);
    assert.equal(result.summary.slope, 2);
    assert.ok(result.files.report.startsWith(c.folder + '/artifacts/'));
    assert.equal(result.artifact.caseId, c.id);
    assert.ok(result.artifact.relatedFiles.includes(result.files.svg));
    assert.equal(result.data, undefined);
    const committed = await git(root, ['show', '--pretty=', '--name-only', 'HEAD']);
    for (const file of Object.values(result.files)) assert.ok(committed.includes(file));
    const oldFit = await fs.readFile(path.join(root, result.files.result), 'utf8');
    await fs.writeFile(path.join(root, 'samples.csv'), 'signal\n5\n99\n');
    const quantified = await tools.get('highzyme_analyze_signal')({ file: 'samples.csv', operation: 'quantify',
      columns: { signal: 'signal' }, parameters: { y_unit: 'a.u.' }, calibration_file: result.files.result }, exec);
    assert.equal(quantified.summary.within_range, 1);
    assert.equal(await fs.readFile(path.join(root, result.files.result), 'utf8'), oldFit);
    const revised = await tools.get('highzyme_analyze_signal')(args, exec);
    assert.equal(revised.files.report, result.files.report);
    assert.equal(p.data.artifacts.length, 2);
    p.fileAccess.denyRead = ['calibration.csv'];
    await assert.rejects(tools.get('highzyme_analyze_signal')(args, exec), /read access/);
    p.fileAccess.denyRead = []; p.fileAccess.denyWrite = [c.folder];
    await assert.rejects(tools.get('highzyme_analyze_signal')(args, exec), /write access/);
    assert.match(deniedTool(p, { name: 'highzyme_analyze_signal' }, root, 'read-only'), /read-only/);
    assert.equal(deniedTool(p, { name: 'highzyme_formulation', arguments: { parameters: {} } }, root, 'read-only'), undefined);
    assert.match(deniedTool(p, { name: 'highzyme_formulation', arguments: { output_prefix: 'artifacts/recipe' } }, root, 'read-only'), /read-only/);
    const schema = fileURLToPath(new URL('./skills/literature-evidence/evidence-schema.md', import.meta.url));
    assert.equal(deniedTool(p, { name: 'read', arguments: { path: schema } }, root, 'workspace-write'), undefined);
    p.operations.network = false;
    await assert.rejects(tools.get('highzyme_retrieve_publication')({ source: '10.1038/s41586-019-1335-8' }, exec), /network access/);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('scientific operation errors preserve the actionable message', async () => {
  await assert.rejects(science({ action: 'identity', formula: 'not-a-formula' }), /formula|element|token|character|syntax/i);
});
