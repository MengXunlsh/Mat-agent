import { promises as fs } from 'node:fs';
import { execFile } from 'node:child_process';
import { git, checkedPath, checkpoint } from './research.mjs';

export async function revisionFiles(root, revision) {
  if (!/^[a-f0-9]{40,64}$/.test(revision)) throw new Error('Invalid revision');
  await git(root, ['cat-file', '-e', revision + '^{commit}']);
  return (await git(root, ['diff-tree', '--root', '--first-parent', '-m', '--no-commit-id', '--name-only', '-r', revision])).split('\n').filter(Boolean);
}
export async function prepareRestore(p, { revision, files, mode = 'restore' }) {
  const available = await revisionFiles(p.root, revision);
  if (!['restore', 'undo'].includes(mode) || !files?.length || files.some(f => !available.includes(f) || f.startsWith('.highzyme/'))) throw new Error('Select changed project files');
  for (const file of files) checkedPath(p.root, file);
  const dirty = await p.changedFiles();
  if (files.some(f => dirty.includes(f))) throw new Error('Save the current changes to these files before restoring');
  const head = await git(p.root, ['rev-parse', 'HEAD']);
  let patch = '';
  if (mode === 'undo') {
    const parent = await git(p.root, ['rev-parse', revision + '^']).catch(() => null);
    const empty = parent ? null : await new Promise((resolve, reject) => {
      const child = execFile('git', ['-C', p.root, 'hash-object', '-t', 'tree', '--stdin'], { windowsHide: true }, (error, stdout) => error ? reject(error) : resolve(stdout.trim()));
      child.stdin.end();
    });
    patch = await git(p.root, ['diff', '--binary', revision, parent || empty, '--', ...files], true);
    if (patch) await applyPatch(p.root, patch, true);
  }
  const diffs = await Promise.all(files.map(async file => {
    const oldText = await git(p.root, ['show', head + ':' + file], true).catch(() => '');
    const newText = mode === 'restore' ? await git(p.root, ['show', revision + ':' + file], true).catch(() => '') : '';
    return { path: file, oldText, newText, binary: oldText.includes('\0') || newText.includes('\0') };
  }));
  return { revision, files, mode, head, diffs, patch };
}
async function applyPatch(root, patch, check = false) {
  await new Promise((resolve, reject) => {
    const child = execFile('git', ['-C', root, 'apply', ...(check ? ['--check'] : []), '--binary', '-'], { windowsHide: true }, error => error ? reject(new Error('This change conflicts with later edits. Restore selected files instead.')) : resolve());
    child.stdin.end(patch);
  });
}
export async function restoreVersion(p, input, owner) {
  const plan = await prepareRestore(p, input);
  if (plan.head !== input.head) throw new Error('The project changed. Preview the restoration again');
  if (plan.mode === 'undo') { if (plan.patch) await applyPatch(p.root, plan.patch); }
  else for (const file of plan.files) {
    const exists = await git(p.root, ['ls-tree', plan.revision, '--', file]);
    if (exists) await git(p.root, ['restore', '--source=' + plan.revision, '--worktree', '--', file]);
    else await fs.rm(checkedPath(p.root, file), { force: true });
  }
  return checkpoint(p.root, (plan.mode === 'undo' ? 'Undo ' : 'Restore ') + plan.revision.slice(0, 8), plan.files, owner);
}
