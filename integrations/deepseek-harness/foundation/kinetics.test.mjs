import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { ResearchProject, deniedTool, git } from './research.mjs';
import { fitProjectKinetics, replotProjectKinetics } from './kinetics.mjs';

test('kinetics exports belong to the case, preserve input and commit together; grants are enforced', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-fit-'));
  try {
    const project = await new ResearchProject({ id: 'project', path: root }).load();
    const researchCase = await project.createCase('Kinetics');
    await project.attachSession(researchCase.id, 'session-kinetics');
    const rows = [.02, .05, .1, .2, .4, .8, 1.6].map(s => `${s},${2.4*s/(.3+s)}`);
    const input = 'concentration,rate\n' + rows.join('\n') + '\n';
    await fs.writeFile(path.join(root, 'rates.csv'), input);
    const args = { file: 'rates.csv', concentration_column: 'concentration', rate_column: 'rate', concentration_unit: 'mM', rate_unit: 'uM/s' };
    const owner = { sessionId: 'session-kinetics', caseId: researchCase.id };
    const result = await fitProjectKinetics(project, args, owner);
    assert.ok(Math.abs(result.fit.km - .3) < 1e-7);
    assert.ok(result.files.report.startsWith(researchCase.folder + '/artifacts/'));
    assert.equal(result.artifact.caseId, researchCase.id);
    const committed = await git(root, ['show', '--pretty=', '--name-only', 'HEAD']);
    for (const file of Object.values(result.files)) assert.ok(committed.includes(file));
    assert.equal(await fs.readFile(path.join(root, 'rates.csv'), 'utf8'), input);
    assert.match(deniedTool(project, { name: 'highzyme_fit_kinetics' }, root, 'read-only'), /read-only/);
    project.fileAccess.denyRead = ['rates.csv'];
    await assert.rejects(fitProjectKinetics(project, args, owner), /read access/);
    project.fileAccess.denyRead = [];
    project.fileAccess.denyWrite = [researchCase.folder];
    await assert.rejects(fitProjectKinetics(project, args, owner), /write access/);
    project.fileAccess.denyWrite = [];
    const revised = await fitProjectKinetics(project, args, owner);
    assert.equal(revised.files.report, result.files.report);
    assert.equal(project.data.artifacts.length, 1);
    const originalFit = await fs.readFile(path.join(root, result.files.result), 'utf8');
    const plot = await replotProjectKinetics(project, { file: result.files.result, labels: ['Test series'] }, owner);
    assert.equal(plot.refitted, false);
    assert.equal(await fs.readFile(path.join(root, result.files.result), 'utf8'), originalFit);
    assert.equal(plot.artifact.caseId, researchCase.id);
    project.fileAccess.denyWrite = [researchCase.folder];
    await assert.rejects(replotProjectKinetics(project, { file: result.files.result }, owner), /write access/);

  } finally { await fs.rm(root, { recursive: true, force: true }); }
});
