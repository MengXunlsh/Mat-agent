import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { ResearchProject, deniedTool, git } from './research.mjs';
import { projectEvidence } from './evidence.mjs';

test('evidence and comparison artifacts retain case ownership, revisions, source grants and Git changes', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-evidence-'));
  try {
    const p = await new ResearchProject({ id: 'test', path: root }).load();
    const c = await p.createCase('Evidence'); await p.attachSession(c.id, 'session');
    const owner = { sessionId: 'session', caseId: c.id };
    await fs.writeFile(path.join(root, 'source.md'), 'Synthetic: Km 0.30 mM; Km 300 uM\n');
    const data = { schema: 'highzyme.evidence.v1', materials: [{ id: 'm', name: 'Synthetic A' }],
      assays: [{ id: 'a', material_id: 'm', label: 'First' }, { id: 'b', material_id: 'm', label: 'Second' }],
      facts: ['a', 'b'].map((id, i) => ({ id, material_id: 'm', assay_id: id, field: 'km', value_raw: i ? '300' : '0.30', unit_raw: i ? 'uM' : 'mM', review: 'supported',
        evidence: [{ file: 'source.md', locator: 'lines[1]', quote: i ? '300 uM' : '0.30 mM' }] })) };
    await fs.writeFile(path.join(root, 'draft.json'), JSON.stringify(data));
    const args = { file: 'draft.json', language: 'zh' };
    const saved = await projectEvidence(p, args, owner, 'save_evidence');
    assert.ok(saved.files.report.startsWith(c.folder + '/artifacts/'));
    const commit = await git(root, ['show', '--pretty=', '--name-only', 'HEAD']);
    for (const file of Object.values(saved.files)) assert.ok(commit.includes(file));
    const comparison = await projectEvidence(p, { selections: [{ file: saved.files.data, assay_ids: ['a', 'b'] }], fields: ['km'], output_prefix: 'assay-check' }, owner, 'compare_evidence');
    assert.equal(comparison.files.report, c.folder + '/artifacts/assay-check-report.md');
    assert.equal(comparison.pairs[0].fields[0].state, 'matched');
    assert.equal(comparison.artifact.caseId, c.id);
    data.title = 'Revised evidence'; await fs.writeFile(path.join(root, 'draft.json'), JSON.stringify(data));
    const revised = await projectEvidence(p, args, owner, 'save_evidence');
    assert.equal(revised.files.report, saved.files.report);
    assert.equal(p.data.artifacts.length, 2);
    p.fileAccess.denyRead = ['source.md'];
    await assert.rejects(projectEvidence(p, args, owner, 'save_evidence'), /read access/);
    p.fileAccess.denyRead = []; p.fileAccess.denyWrite = [c.folder];
    await assert.rejects(projectEvidence(p, args, owner, 'save_evidence'), /write access/);
    for (const name of ['highzyme_evidence_save', 'highzyme_compare_evidence', 'highzyme_replot_kinetics']) assert.match(deniedTool(p, { name }, root, 'read-only'), /read-only/);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});
