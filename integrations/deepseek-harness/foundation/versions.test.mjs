import test from 'node:test';
import assert from 'node:assert/strict';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ResearchProject, checkpoint, git } from './research.mjs';
import { prepareRestore, restoreVersion } from './versions.mjs';

test('selected file restoration preserves other files and creates an attributed commit', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hz-restore-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const p = await new ResearchProject({ id: 'p', path: root }).load();
  await git(root, ['init']);
  await git(root, ['config', 'core.autocrlf', 'false']);
  await fs.writeFile(path.join(root, 'plan.md'), 'original\n');
  const first = await checkpoint(root, 'Initial', ['plan.md'], { sessionId: 'a' });
  await fs.writeFile(path.join(root, 'plan.md'), 'changed\n');
  await fs.writeFile(path.join(root, 'other.md'), 'keep\n');
  await checkpoint(root, 'Change', ['plan.md', 'other.md'], { sessionId: 'b' });
  const plan = await prepareRestore(p, { revision: first.revision, files: ['plan.md'] });
  await restoreVersion(p, plan, { sessionId: 'a' });
  assert.equal(await fs.readFile(path.join(root, 'plan.md'), 'utf8'), 'original\n');
  assert.equal(await fs.readFile(path.join(root, 'other.md'), 'utf8'), 'keep\n');
  assert.equal((await p.history())[0].sessionId, 'a');
  await fs.writeFile(path.join(root, 'plan.md'), 'unsaved\n');
  await assert.rejects(prepareRestore(p, { revision: first.revision, files: ['plan.md'] }), /Save the current/);
});

test('undo preserves a later independent change and rejects overlapping edits without mutation', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hz-undo-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const p = await new ResearchProject({ id: 'p', path: root }).load();
  await git(root, ['init']);
  await git(root, ['config', 'core.autocrlf', 'false']);
  await fs.writeFile(path.join(root, 'a.txt'), 'one\n');
  await checkpoint(root, 'Initial', ['a.txt']);
  await fs.writeFile(path.join(root, 'a.txt'), 'two\n');
  const changed = await checkpoint(root, 'Second', ['a.txt']);
  await fs.writeFile(path.join(root, 'b.txt'), 'later\n');
  await checkpoint(root, 'Later', ['b.txt']);
  await restoreVersion(p, await prepareRestore(p, { revision: changed.revision, files: ['a.txt'], mode: 'undo' }), { sessionId: 'a' });
  assert.equal(await fs.readFile(path.join(root, 'a.txt'), 'utf8'), 'one\n');
  assert.equal(await fs.readFile(path.join(root, 'b.txt'), 'utf8'), 'later\n');
  await assert.rejects(prepareRestore(p, { revision: changed.revision, files: ['a.txt'], mode: 'undo' }), /conflicts/);
  assert.equal(await git(root, ['status', '--porcelain']), '');
});
