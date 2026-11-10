import test from 'node:test';
import assert from 'node:assert/strict';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ResearchProject, checkpoint, git, deniedTool, checkedPath, parseArtifactDraft, selectDiscussion, discussionTurns, projectContext } from './research.mjs';

async function fixture(callback) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-local-'));
  try { await callback(await new ResearchProject({ id: 'project', path: root }).load()); }
  finally { await fs.rm(root, { recursive: true, force: true }); }
}

test('fresh case context is lossless JSON and omits repeated bundle metadata', () => fixture(async p => {
  const c = await p.createCase('Fresh context');
  const context = projectContext(p, c, { researchWorkflow: { file: c.research?.file || null, skill: null } });
  assert.deepEqual(JSON.parse(JSON.stringify(context)), context);
  assert.equal(context.directory, p.root);
  assert.equal(context.researchWorkflow.file, null);
  assert.equal(context.case.folder, c.folder);
}));
test('ordinary conversations stay independent; cases archive, trash and restore without losing files', () => fixture(async p => {
  assert.equal(p.caseFor({ id: 'discussion', header: { cwd: p.root } }), undefined);
  const c = await p.createCase('研究 A'); await p.attachSession(c.id, 'session-a');
  const file = checkedPath(p.root, c.folder + '/result.txt'); await fs.writeFile(file, '55');
  for (const status of ['archived', 'trash', 'active']) {
    await p.updateCase(c.id, { status }); const reopened = await new ResearchProject({ id: p.id, path: p.root }).load();
    assert.equal(reopened.case(c.id).status, status); assert.equal(await fs.readFile(file, 'utf8'), '55');
  }
  assert.equal(p.caseFor({ id: 'session-a' }).id, c.id);
  const other = await p.createCase('B'); await assert.rejects(p.attachSession(other.id, 'session-a'), /another case/);
}));

test('case folders use readable English keywords and stay stable when the title changes', () => fixture(async p => {
  const automatic=await p.createCase('Charge Analysis');
  assert.match(automatic.folder,/^cases\/charge-analysis-[a-f0-9]{8}$/);
  const custom=await p.createCase('电荷分析','h2-charge');
  assert.match(custom.folder,/^cases\/h2-charge-[a-f0-9]{8}$/);
  await p.updateCase(custom.id,{title:'新的案例名称'});
  const reopened=await new ResearchProject({id:p.id,path:p.root}).load();
  assert.equal(reopened.case(custom.id).folder,custom.folder);
  await assert.rejects(p.createCase('Invalid','../case'),/English keywords/);
}));
test('artifact references pin real Git content across edits and restart; project Git config is preserved', () => fixture(async p => {
  const c = await p.createCase('Case');
  const first = await p.publish({ title: 'Plan', content: '# Original\nData: 1', sessionId: 'discussion' });
  assert.equal(await git(p.root, ['status', '--porcelain']), '');
  await git(p.root, ['config', 'highzyme.test', 'keep-me']);
  await p.reference(c.id, first.id);
  const second = await p.publish({ title: 'Plan', file: first.file, content: '# Revised\nData: 2', sessionId: 'discussion' });
  assert.equal((await p.readArtifact(second.id, c.id)).content, '# Original\nData: 1');
  const reopened = await new ResearchProject({ id: p.id, path: p.root }).load();
  assert.equal((await reopened.readArtifact(second.id)).content, '# Revised\nData: 2');
  assert.equal(await git(p.root, ['config', 'highzyme.test']), 'keep-me');
  await checkpoint(p.root, 'Record adoption'); const count = await git(p.root, ['rev-list', '--count', 'HEAD']);
  assert.equal((await checkpoint(p.root, 'No changes')).changed, false);
  assert.equal(await git(p.root, ['rev-list', '--count', 'HEAD']), count);
}));
test('content and write grants also restrict Shell, inherited agents and custom mutation tools', () => fixture(async p => {
  await p.setAccess({ content: 'selected', read: ['sources'], write: ['results'], shell: true, network: true, compute: false });
  assert.equal(p.access.shell, false);
    assert.equal(deniedTool(p, { name: 'web_search', arguments: { query: 'nanozyme' } }, p.root), undefined);
    assert.equal(deniedTool(p, { name: 'web_fetch', arguments: { url: 'https://example.org' } }, p.root), undefined);
    assert.ok(deniedTool({ ...p, access: { ...p.access, network: false } }, { name: 'web_search' }, p.root));
  const denied = (name, args = {}, mode) => deniedTool(p, { name, arguments: args }, p.root, mode);
  assert.equal(denied('read', { path: 'sources/paper.txt' }), undefined);
  assert.ok(denied('read', { path: 'private.txt' })); assert.ok(denied('grep', { path: '.' })); assert.ok(denied('pwsh'));
  assert.equal(denied('write', { path: 'results/notes.md' }), undefined);
  assert.ok(denied('write', { path: 'sources/paper.txt' })); assert.ok(denied('highzyme_compute_submit'));
  assert.ok(denied('highzyme_artifact_save', {}, 'read-only'));
  assert.ok(denied('highzyme_chemical_identity', { smiles: 'CCO', output_prefix: 'ethanol' }, 'read-only'));
  assert.equal(denied('highzyme_chemical_identity', { smiles: 'CCO' }, 'read-only'), undefined);
  assert.equal(denied('terminal_close'), undefined); assert.equal(denied('interrupt_agent'), undefined);
  await p.setAccess({ content: 'project', read: [], write: ['.'], shell: true, network: true, compute: false });
  assert.equal(denied('pwsh'), undefined);
  p.operations.network = false; assert.equal(p.access.shell, false); assert.ok(denied('web'));
}));
test('job identity survives reopening without issuing any network requests', () => fixture(async p => {
  await p.saveJob({ id: 'job_123', type: 'compute', resource_id: 'resource', status: 'running' });
  const reopened = await new ResearchProject({ id: p.id, path: p.root }).load();
  assert.deepEqual(await reopened.jobs(), [{ id: 'job_123', type: 'compute', resource_id: 'resource', status: 'running' }]);
  for (const rel of ['../escape', 'C:/file', '/outside', 'a/../../b']) assert.throws(() => checkedPath(p.root, rel));
}));
test('one project grant applies across cases; old task overrides are no longer active', () => fixture(async p => {
  await fs.mkdir(path.dirname(p.accessFile), { recursive: true });
  await fs.writeFile(p.accessFile, JSON.stringify({ ...p.access, targets: { 'session:old': { content: 'selected', read: [] } } }));
  await p.load();
  assert.equal(p.permitted('sources/private.txt'), true);
  await p.setAccess({ ...p.access, denyRead: ['sources'], read: ['sources/public.txt'] });
  assert.equal(p.permitted('sources/private.txt'), false);
  assert.equal(p.permitted('sources/public.txt'), true);
  assert.equal(p.access.shell, false);
  const reopened = await new ResearchProject({ id: p.id, path: p.root }).load();
  assert.equal(reopened.permitted('sources/private.txt'), false);
  assert.equal('targets' in JSON.parse(await fs.readFile(p.accessFile, 'utf8')), false);
  await reopened.setAccess({ ...reopened.access, denyRead: [] });
  assert.equal(reopened.permitted('sources/private.txt'), true);
  assert.equal(reopened.access.shell, true);
}));
test('artifact source messages and exact text survive Git saves', () => fixture(async p => {
  const text = '\n    indented code\n\n';
  const item = await p.publish({ title: 'Discussion', content: text, sessionId: 'session-a', sourceMessageIds: ['first', 'last'] });
  assert.equal((await p.readArtifact(item.id)).content, text);
  assert.deepEqual(item.sourceMessageIds, ['first', 'last']);
}));
test('English artifact folders, collision handling, case paths and task-attributed Git revisions', () => fixture(async p => {
  const first = await p.publish({ title: '动力学讨论', fileStem: 'pod-kinetics-summary', content: '# A', sessionId: 'review' });
  assert.equal(first.file, 'artifacts/pod-kinetics-summary/pod-kinetics-summary.md');
  const second = await p.publish({ title: '另一份记录', fileStem: 'pod-kinetics-summary', content: '# B', sessionId: 'review' });
  assert.equal(second.file, 'artifacts/pod-kinetics-summary/pod-kinetics-summary-2.md');
  const c = await p.createCase('研究案例'); await p.attachSession(c.id, 'case-chat');
  const plan = await p.publish({ title: '验证方案', fileStem: 'validation-plan', kind: 'plan', content: '# C', sessionId: 'case-chat', caseId: c.id });
  assert.equal(plan.file, c.folder + '/artifacts/validation-plan.md');
  const revised = await p.publish({ ...first, content: '# Revised', checkpointOwner: { sessionId: 'case-chat', caseId: c.id } });
  assert.equal(revised.file, first.file);
  assert.equal(revised.sessionId, 'review');
  const history = await p.history();
  assert.equal(history[0].caseId, c.id); assert.equal(history[0].sessionId, 'case-chat');
  assert.equal(history.at(-1).sessionId, 'review');
  await assert.rejects(p.publish({ title: '脚本', kind: 'code', content: 'print(1)' }), /native code/);
  await fs.writeFile(path.join(p.root, 'unrelated.txt'), 'keep uncommitted');
  await fs.writeFile(path.join(p.root, 'analysis.py'), 'print(55)');
  await checkpoint(p.root, 'Analysis script', ['analysis.py'], { sessionId: 'review' });
  assert.match(await git(p.root, ['status', '--porcelain']), /unrelated.txt/);
  assert.doesNotMatch(await git(p.root, ['show', '--stat', 'HEAD']), /unrelated.txt/);
}));
test('current changes include initial files and staged additions without including credentials', () => fixture(async p => {
  await fs.writeFile(path.join(p.root, 'notes.md'), '# Research notes');
  await fs.writeFile(path.join(p.root, '.env'), 'LOCAL_TEST_PLACEHOLDER=1');
  assert.deepEqual(await p.changedFiles(), ['notes.md']);
  await checkpoint(p.root, 'Start notes', ['notes.md'], { sessionId: 'discussion' });
  await fs.writeFile(path.join(p.root, 'results.csv'), 'value\n1\n');
  await git(p.root, ['add', '--', 'results.csv']);
  assert.deepEqual(await p.changedFiles(), ['results.csv']);
  await fs.rm(path.join(p.root, 'notes.md'));
  assert.deepEqual((await p.changedFiles()).sort(), ['notes.md', 'results.csv']);
}));

test('discussion defaults to the last round and keeps all replies within that round', () => {
  const messages = [{ id: 'orphan', role: 'assistant', text: 'Earlier inherited answer' },
    ...Array.from({ length: 17 }, (_, i) => [{ id: 'u' + i, role: 'user', text: 'Question ' + i }, { id: 'a' + i, role: 'assistant', text: 'Answer ' + i }]).flat(),
    { id: 'final', role: 'assistant', text: 'Additional reply' }];
  assert.equal(discussionTurns(messages).length, 17);
  assert.deepEqual(selectDiscussion(messages).map(m => m.id), ['u16', 'a16', 'final']);
  assert.equal(selectDiscussion(messages, { rounds: 15 }).length, 31);
  assert.deepEqual(selectDiscussion(messages, { messageIds: ['a3', 'u0'] }).map(m => m.id), ['u0', 'a3']);
  for (const rounds of [0, 16, 1.5, '15']) assert.throws(() => selectDiscussion(messages, { rounds }), /1 to 15/);
  assert.throws(() => selectDiscussion(messages, { messageIds: Array.from({ length: 16 }, (_, i) => 'u' + i) }), /15 rounds/);
  assert.throws(() => selectDiscussion(messages, { messageIds: ['missing'] }), /Unknown/);
  assert.throws(() => selectDiscussion(messages, { messageIds: [] }), /Select discussion/);
});

test('artifact editor output accepts real metadata and rejects invented message IDs or sources', () => {
  const messages = [{ id: 'm1', text: 'pH 4.0, 25 C; https://example.org/source' }];
  const draft = { title: '测试记录', file_stem: 'pod-assay-notes', kind: 'source', content: '# Notes\npH 4.0, 25 C', source_message_ids: ['m1'], source_references: ['https://example.org/source'] };
  assert.equal(parseArtifactDraft('```json\n' + JSON.stringify(draft) + '\n```', messages).fileStem, 'pod-assay-notes');
  assert.throws(() => parseArtifactDraft(JSON.stringify({ ...draft, source_message_ids: ['missing'] }), messages), /unknown source messages/);
  assert.throws(() => parseArtifactDraft(JSON.stringify({ ...draft, file_stem: '中文名称' }), messages), /English keyword/);
  assert.throws(() => parseArtifactDraft(JSON.stringify({ ...draft, source_references: ['invented'] }), messages), /unknown source references/);
});
