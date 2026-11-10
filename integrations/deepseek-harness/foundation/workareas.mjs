import path from 'node:path';
import { promises as fs } from 'node:fs';
import { ResearchProject, git, checkedPath, contains, checkpoint } from './research.mjs';
import { readJson, writeJson } from './state.mjs';

export class Workareas {
  constructor(project, workingDirectory) { this.workingDirectory = workingDirectory; this.project = project; this.file = path.join(project.root, '.highzyme', 'workareas.local.json'); this.rows = []; this.views = new Map(); }
  async load() { this.rows = await readJson(this.file, []); return this; }
  async save() { await writeJson(this.file, this.rows); }
  row(sessionId) { return this.rows.find(r => r.sessionId === sessionId); }
  async view(sessionId) {
    const row = this.row(sessionId); if (!row?.active) return this.project;
    if (!this.views.has(row.path)) this.views.set(row.path, await new ResearchProject({ id: this.project.id, path: row.path }, this.project.operations).load());
    const view = this.views.get(row.path); view.fileAccess = this.project.fileAccess; return view;
  }
  current(sessionId) { const row = this.row(sessionId); return row?.active ? this.views.get(row.path) || this.project : this.project; }
  async create(agent, name, service) {
    if (this.row(agent.session.id)) throw new Error('Remove the existing independent workspace before creating another');
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name || '')) throw new Error('Use lowercase English keywords for the workspace name');
    if ((await this.project.changedFiles()).filter(f => !f.startsWith('.highzyme/')).length) throw new Error('Save project file changes before creating an independent workspace');
    if (!service) throw new Error('The independent workspace service is unavailable');
    await this.project.save();
    await checkpoint(this.project.root, 'Prepare independent workspace', ['.highzyme/project.json'], { sessionId: agent.session.id, caseId: this.project.caseFor(agent.session)?.id });
    const previous = this.workingDirectory.get(agent.session);
    await this.workingDirectory.set(agent, this.project.root);
    let result;
    try { result = await service.create(agent, { name: 'highzyme/' + name }); }
    catch (error) { await this.workingDirectory.set(agent, previous); throw error; }
    const row = { ...result, sessionId: agent.session.id, active: true, createdAt: Date.now() };
    this.rows.push(row); await this.save();
    await this.view(row.sessionId); return row;
  }
  async compare(sessionId) {
    const row = this.row(sessionId); if (!row) throw new Error('Independent workspace not found');
    return { ...row, files: (await git(this.project.root, ['diff', '--name-only', 'HEAD...' + row.branch])).split('\n').filter(Boolean), diff: await git(this.project.root, ['diff', 'HEAD...' + row.branch], true) };
  }
  async merge(sessionId, owner) {
    const row = this.row(sessionId); if (!row) throw new Error('Independent workspace not found');
    if ((await this.project.changedFiles()).length || (await (await this.viewForRow(row)).changedFiles()).length) throw new Error('Save file changes in both workspaces before merging');
    try { await git(this.project.root, ['merge', '--no-commit', '--no-ff', row.branch]); }
    catch (error) {
      const conflicts = await git(this.project.root, ['diff', '--name-only', '--diff-filter=U']);
      await git(this.project.root, ['merge', '--abort']).catch(() => {});
      throw new Error('Merge conflict: ' + (conflicts || error.message));
    }
    const merging = await git(this.project.root, ['rev-parse', '-q', '--verify', 'MERGE_HEAD']).catch(() => '');
    if (merging) await git(this.project.root, ['-c', 'user.name=Highzyme', '-c', 'user.email=local@highzyme.invalid', 'commit', '-m', 'Merge ' + row.branch + '\n\nHighzyme-Session: ' + owner.sessionId + (owner.caseId ? '\nHighzyme-Case: ' + owner.caseId : '')]);
    await this.project.load(); return { merged: true };
  }
  async viewForRow(row) { return new ResearchProject({ id: this.project.id, path: row.path }, this.project.operations).load(); }
  async activate(agent, active) {
    const row = this.row(agent.session.id); if (!row) throw new Error('Independent workspace not found');
    await this.workingDirectory.set(agent, active ? row.path : this.project.root);
    row.active = active; await this.save(); if (active) await this.view(row.sessionId); return row;
  }
  async remove(agent) {
    const row = this.row(agent.session.id); if (!row) throw new Error('Independent workspace not found');
    if ((await (await this.viewForRow(row)).changedFiles()).length) throw new Error('Save or discard workspace changes before removing it');
    await git(this.project.root, ['merge-base', '--is-ancestor', row.branch, 'HEAD']).catch(() => { throw new Error('Merge workspace changes before removing it'); });
    const real = await fs.realpath(row.path), root = await fs.realpath(this.project.root);
    if (!contains(root, real) || !real.includes(path.join('.agents', 'worktrees'))) throw new Error('Invalid managed workspace location');
    await this.activate(agent, false);
    await git(this.project.root, ['worktree', 'remove', '--', row.path]);
    await git(this.project.root, ['branch', '-d', row.branch]);
    this.rows = this.rows.filter(r => r !== row); this.views.delete(row.path); await this.save(); return { removed: true };
  }
}
