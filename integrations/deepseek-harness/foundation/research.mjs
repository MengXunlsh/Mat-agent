import { promises as fs, realpathSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID, createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { isUtf8 } from 'node:buffer';
import { inside, readJson, writeJson } from './state.mjs';

const run = promisify(execFile);
const bundledSkills = fileURLToPath(new URL('./skills', import.meta.url)).replace(/[\\/]$/, '');
export const DEFAULT_ACCESS = { content: 'project', read: [], write: ['.'], denyRead: [], denyWrite: [] };
export const DEFAULT_OPERATIONS = { shell: true, network: true, compute: false };
export const englishStem = value => String(value || '').toLowerCase().match(/[a-z0-9]+/g)?.slice(0, 8).join('-') || 'research-note';
const matches = (rule, file) => rule === '.' || rule === file || file.startsWith(rule.replace(/\/$/, '') + '/');
export const contains = (root, file) => file === root || file.startsWith(root + path.sep);
export function checkedPath(root, relative) {
  const target = inside(root, relative);
  let existing = target;
  while (!existsSync(existing)) existing = path.dirname(existing);
  if (!contains(realpathSync(root), realpathSync(existing))) throw new Error('Path resolves outside the project');
  return target;
}
const gitArgs = ['-c', 'maintenance.auto=false', '-c', 'gc.auto=0', '-c', 'core.quotepath=false'];
export async function git(root, args, raw = false) {
  const output = (await run('git', [...gitArgs, '-C', root, ...args], { windowsHide: true, maxBuffer: 8 * 1024 ** 2 })).stdout;
  return raw ? output : output.trim();
}
async function ensureProjectGit(root) {
  if (!existsSync(path.join(root, '.git'))) await git(root, ['init', '--quiet']);
  const exclude = await git(root, ['rev-parse', '--git-path', 'info/exclude']);
  const excludePath = path.resolve(root, exclude);
  const old = await fs.readFile(excludePath, 'utf8').catch(e => { if (e.code === 'ENOENT') return ''; throw e; });
  if (!old.includes('# Highzyme local state')) {
    await fs.mkdir(path.dirname(excludePath), { recursive: true });
    await fs.writeFile(excludePath, old + '\n# Highzyme local state\n.env\n.env.*\n*.pem\n*.key\nnode_modules/\n.venv/\n__pycache__/\n.highzyme/access.local.json\n.highzyme/jobs/\n.highzyme/sessions/\n');
  }
  const exclusions = '\n# Highzyme memory and workspaces\n.highzyme/memory.jsonl\n.highzyme/memory-settings.json\n.highzyme/workareas.local.json\n.agents/worktrees/\n';
  if (!old.includes('# Highzyme memory and workspaces')) await fs.appendFile(excludePath, exclusions);
  if (!old.includes('.highzyme/reference-files/')) await fs.appendFile(excludePath, '\n.highzyme/reference-files/\n');
}
export async function checkpoint(root, message, paths, owner = {}) {
  if (!message?.trim()) throw new Error('A version description is required');
  await ensureProjectGit(root);
  const selected = paths?.length ? paths.map(p => { checkedPath(root, p); return p; }) : ['.'];
  await git(root, ['add', '--', ...selected]);
  const changed = await git(root, ['diff', '--cached', '--name-only', '--', ...selected]);
  const trailers = [['Highzyme-Session', owner.sessionId], ['Highzyme-Case', owner.caseId]].filter(([, value]) => value).map(([key, value]) => key + ': ' + value).join('\n');
  const commitMessage = message.trim().slice(0, 240) + (trailers ? '\n\n' + trailers : '');
  if (changed) await git(root, ['-c', 'user.name=Highzyme', '-c', 'user.email=local@highzyme.invalid', 'commit', '--only', '-m', commitMessage, '--', ...selected]);
  const revision = await git(root, ['rev-parse', 'HEAD']).catch(() => null);
  return { revision, changed: !!changed };
}

export function projectContext(project, researchCase, extra = {}) {
  const c = researchCase;
  return { projectId: project.id, directory: project.root,
    pathBase: 'All relative paths, including native file tools, resolve from directory. Case outputs belong in artifactDirectory.',
    case: c ? { id: c.id, title: c.title, folder: c.folder, status: c.status,
      references: (c.references || []).map(r => ({ artifactId: r.artifactId, title: r.title, file: r.file, revision: r.revision })) } : null,
    access: project.access,
    artifacts: project.data.artifacts.filter(a => project.permitted(a.file)).map(a => ({ id: a.id, title: a.title, file: a.file, kind: a.kind, revision: a.revision || null })),
    ...extra };
}

/** Research metadata over native directories; no copying or second project registry. */
export class ResearchProject {
  constructor(workspace, operations = { ...DEFAULT_OPERATIONS }) {
    this.id = workspace.id; this.root = workspace.path;
    this.file = path.join(this.root, '.highzyme', 'project.json');
    this.accessFile = path.join(this.root, '.highzyme', 'access.local.json');
    this.data = { format: 'highzyme-research-project', version: 2, cases: [], artifacts: [] };
    this.fileAccess = structuredClone(DEFAULT_ACCESS);
    this.operations = operations;
    this.tail = Promise.resolve();
  }
  async load() {
    const data = await readJson(this.file, null);
    if (data?.format === 'highzyme-research-project') {
      this.data = data;
      for (const artifact of this.data.artifacts) artifact.revision = await this.artifactRevision(artifact);
    }
    const access = await readJson(this.accessFile, {});
    this.fileAccess = Object.fromEntries(Object.entries(DEFAULT_ACCESS).map(([key, fallback]) => [key, access[key] ?? structuredClone(fallback)]));
    return this;
  }
  get access() {
    const access = { ...this.fileAccess, ...this.operations };
    if (access.content === 'selected' || access.denyRead.length || access.denyWrite.length || !access.write.includes('.') || !access.network) access.shell = false;
    return access;
  }
  mutate(callback) {
    const result = this.tail.then(callback);
    this.tail = result.catch(() => {});
    return result;
  }
  async save() {
    // A commit cannot contain its own hash. Resolve current artifact versions
    // from Git on load; case references retain their explicit content revision.
    const data = structuredClone(this.data);
    for (const artifact of data.artifacts) delete artifact.revision;
    await writeJson(this.file, data);
  }
  case(id) { const row = this.data.cases.find(c => c.id === id); if (!row) throw new Error('Case not found'); return row; }
  caseFor(session) { return this.data.cases.find(c => c.sessions.includes(session?.id) || (session?.header.cwd && contains(path.join(this.root, c.folder), session.header.cwd))); }
  async createCase(title, folderName) {
    if (!title?.trim()) throw new Error('Enter a case name');
    if (folderName && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(folderName)) throw new Error('Use lowercase English keywords for the case folder');
    const keywords = (folderName || title.toLowerCase().match(/[a-z0-9]+/g)?.slice(0, 8).join('-') || 'case').slice(0, 64).replace(/-$/, '');
    const id = randomUUID(), row = { id, title: title.trim().slice(0, 160), folder: 'cases/' + keywords + '-' + id.slice(0, 8), status: 'active', sessions: [], references: [], createdAt: Date.now() };
    await fs.mkdir(checkedPath(this.root, row.folder), { recursive: true });
    this.data.cases.push(row); await this.save(); return row;
  }
  async updateCase(id, changes) {
    const row = this.case(id);
    if (changes.title !== undefined) { if (!changes.title.trim()) throw new Error('Enter a case name'); row.title = changes.title.trim().slice(0, 160); }
    if (changes.status !== undefined) {
      if (!['active', 'archived', 'trash'].includes(changes.status)) throw new Error('Invalid case state');
      row.status = changes.status;
    }
    row.updatedAt = Date.now(); await this.save(); return row;
  }
  async attachSession(caseId, sessionId) {
    const row = this.case(caseId);
    if (row.status !== 'active') throw new Error('Restore this case before continuing');
    const previous = this.data.cases.find(c => c.sessions.includes(sessionId));
    if (previous && previous !== row) throw new Error('The conversation already belongs to another case');
    if (!row.sessions.includes(sessionId)) row.sessions.push(sessionId);
    await this.save(); return row;
  }
  permitted(relative, operation = 'read') {
    const snapshot = relative.match(/^\.highzyme\/reference-files\/[a-f0-9]{40,64}\/[a-zA-Z0-9-]+\/(.+)$/);
    if (snapshot) {
      if (operation === 'write') return false;
      relative = snapshot[1];
    }
    const rules = operation === 'write' ? this.access.write : this.access.read;
    const score = list => Math.max(-1, ...list.filter(p => matches(p, relative)).map(p => p === '.' ? 0 : p.length));
    const allowed = Math.max(operation === 'read' && this.access.content === 'project' ? 0 : -1, score(rules));
    const denied = score(operation === 'write' ? this.access.denyWrite : this.access.denyRead);
    return allowed > denied;
  }
  async setAccess(input) {
    if (!['project', 'selected'].includes(input.content)) throw new Error('Invalid content policy');
    const normalize = list => [...new Set((list || []).map(p => String(p).trim().replaceAll('\\', '/').replace(/\/$/, '')).filter(Boolean))].map(p => { if (p !== '.') checkedPath(this.root, p); return p; });
    this.fileAccess = { content: input.content, read: normalize(input.read), write: normalize(input.write), denyRead: normalize(input.denyRead), denyWrite: normalize(input.denyWrite) };
    await writeJson(this.accessFile, this.fileAccess); return this.access;
  }
  async artifactPath({ file, fileStem, title, content, kind = 'source', sessionId, caseId }) {
    if (file) { checkedPath(this.root, file); return file; }
    if (['code', 'data'].includes(kind)) throw new Error('Specify the native code or data filename');
    const stem = englishStem(fileStem || title);
    if (fileStem && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(fileStem)) throw new Error('Use lowercase English keywords for the filename');
    let folder = 'artifacts';
    if (caseId) folder = this.case(caseId).folder + '/artifacts';
    else if (sessionId) {
      this.data.artifactFolders ||= {};
      if (!this.data.artifactFolders[sessionId]) {
        const name = stem.split('-').slice(0, 3).join('-');
        let unique = name, n = 2;
        while (Object.values(this.data.artifactFolders).includes(unique) || existsSync(checkedPath(this.root, 'artifacts/' + unique))) unique = name + '-' + n++;
        this.data.artifactFolders[sessionId] = unique;
      }
      folder += '/' + this.data.artifactFolders[sessionId];
    }
    let destination = folder + '/' + stem + '.md', n = 2;
    while (existsSync(checkedPath(this.root, destination))) destination = folder + '/' + stem + '-' + n++ + '.md';
    return destination;
  }
  async publish({ artifactId, title, file, fileStem, content, kind, sessionId, caseId, sourceMessageIds, sourceReferences, relatedFiles, files, analysis, validation, checkpointOwner, enforceGrant = false }) {
    const previous = artifactId ? this.data.artifacts.find(a => a.id === artifactId) : file ? this.data.artifacts.find(a => a.file === file) : null;
    if (artifactId && !previous) throw new Error('Artifact not found');
    if (previous && file && previous.file !== file) throw new Error('A revision keeps the existing artifact path');
    file ||= previous?.file;
    title ??= previous?.title;
    kind ??= previous?.kind || 'source';
    sessionId ??= previous?.sessionId || null; caseId ??= previous?.caseId || null;
    checkpointOwner ||= { sessionId, caseId };
    sourceMessageIds ??= previous?.sourceMessageIds || []; sourceReferences ??= previous?.sourceReferences || [];
    files ??= relatedFiles ? Object.fromEntries(Object.entries(previous?.files || {}).filter(([, member]) => [file, ...relatedFiles].includes(member))) : previous?.files || {};
    analysis ??= previous?.analysis; validation ??= previous?.validation;
    if (validation) sourceReferences = [...new Set([...sourceReferences, validation.source.artifact_id])];
    if (Object.values(files).some(member => typeof member !== 'string')) throw new Error('Output roles must point to relative file paths');
    if (!title?.trim() || !['source', 'plan', 'result', 'code', 'data'].includes(kind)) throw new Error('Enter a title and valid artifact type');
    const id = previous?.id || randomUUID();
    file = await this.artifactPath({ file, fileStem, title, content, kind, sessionId, caseId });
    relatedFiles = [...new Set([file, ...(relatedFiles ?? previous?.relatedFiles ?? []), ...Object.values(files)])];
    for (const member of relatedFiles) {
      const destination = checkedPath(this.root, member);
      if (enforceGrant && (!this.permitted(member, 'write') || ((member !== file || content === undefined) && !this.permitted(member)))) throw new Error('Grant access to the artifact file: ' + member);
      if (member !== file || content === undefined) if (!(await fs.stat(destination)).isFile()) throw new Error('Select an existing artifact file: ' + member);
    }
    const target = checkedPath(this.root, file);
    if (content !== undefined) { await fs.mkdir(path.dirname(target), { recursive: true }); await fs.writeFile(target, content, 'utf8'); }
    const info = await fs.stat(target);
    if (!info.isFile()) throw new Error('Select a file');
    const sha256 = createHash('sha256').update(await fs.readFile(target)).digest('hex');
    const row = { id, title: title.trim(), file, kind, sessionId, caseId, sourceMessageIds, sourceReferences,
      relatedFiles, files, ...(validation ? { validation } : {}), ...(analysis ? { analysis } : {}), sha256, updatedAt: Date.now(), createdAt: previous?.createdAt || Date.now() };
    const saved = previous ? Object.assign(previous, row) : row;
    if (!previous) this.data.artifacts.push(saved);
    await this.save();
    const version = await checkpoint(this.root, 'Artifact: ' + row.title, [...relatedFiles, '.highzyme/project.json'], checkpointOwner);
    saved.revision = version.revision;
    // The index describes the content commit; references pin that commit below.
    await this.save(); return saved;
  }
  async reference(caseId, artifactId) {
    const row = this.case(caseId), artifact = this.data.artifacts.find(a => a.id === artifactId);
    if (!artifact?.revision) throw new Error('Save an artifact version first');
    const saved = await this.readArtifact(artifactId, undefined, false, { maxChars: 1 });
    const ref = { artifactId, file: artifact.file, title: artifact.title, revision: saved.revision, sha256: saved.sha256,
      relatedFiles: [...saved.relatedFiles], files: { ...saved.files }, ...(saved.validation ? { validation: saved.validation } : {}), addedAt: Date.now() };
    row.references = row.references.filter(r => r.artifactId !== artifactId).concat(ref);
    await this.save(); return ref;
  }
  async artifactRevision(artifact) {
    return git(this.root, ['log', '-1', '--format=%H', '--', ...(artifact.relatedFiles || [artifact.file])]).catch(() => artifact.revision || null);
  }
  async readArtifact(id, caseId, enforceGrant = true, options = {}) {
    if (options.offset !== undefined && (!Number.isInteger(options.offset) || options.offset < 0) || options.maxChars !== undefined && (!Number.isInteger(options.maxChars) || options.maxChars < 1 || options.maxChars > 64000)) throw new Error('Use a nonnegative offset and a text limit from 1 to 64000');
    const artifact = this.data.artifacts.find(a => a.id === id);
    if (!artifact) throw new Error('Artifact not found');
    let ref = caseId ? this.case(caseId).references.find(r => r.artifactId === id) : { ...artifact, revision: await this.artifactRevision(artifact) };
    if (!ref) throw new Error('This case does not reference that artifact');
    if (!/^[a-f0-9]{40,64}$/.test(ref.revision)) throw new Error('Artifact has no saved version');
    if (!ref.relatedFiles) {
      const index = await git(this.root, ['show', ref.revision + ':.highzyme/project.json'], true).then(JSON.parse).catch(() => null);
      const saved = index?.artifacts.find(a => a.id === id);
      ref = { ...saved, ...ref, relatedFiles: saved?.relatedFiles || [ref.file], files: saved?.files || {} };
    }
    let file = ref.files?.[options.file] || options.file || ref.file;
    if (!ref.relatedFiles.includes(file)) {
      const matches = ref.relatedFiles.filter(member => path.posix.basename(member) === file);
      if (matches.length === 1) file = matches[0];
      else throw new Error('Select a file from this artifact version: ' + ref.relatedFiles.join(', '));
    }
    if (enforceGrant && !this.permitted(file)) throw new Error('Grant Agent access to this file first');
    checkedPath(this.root, file);
    const relatedFiles = ref.relatedFiles.filter(member => !enforceGrant || this.permitted(member));
    const files = Object.fromEntries(Object.entries(ref.files || {}).filter(([, member]) => relatedFiles.includes(member)));
    const metadata = { ...ref, file, relatedFiles, files, mainFile: ref.file };
    if (options.metadataOnly) return metadata;
    const blob = (await run('git', [...gitArgs, '-C', this.root, 'cat-file', 'blob', ref.revision + ':' + file], { windowsHide: true, encoding: 'buffer', maxBuffer: 64 * 1024 ** 2 })).stdout;
    const result = { ...metadata, bytes: blob.length, sha256: createHash('sha256').update(blob).digest('hex'), binary: blob.includes(0) || !isUtf8(blob) };
    if (options.materialize) {
      await ensureProjectGit(this.root);
      const localFile = '.highzyme/reference-files/' + ref.revision + '/' + id + '/' + file;
      const target = checkedPath(this.root, localFile);
      await fs.mkdir(path.dirname(target), { recursive: true });
      if (existsSync(target)) await fs.chmod(target, 0o644);
      await fs.writeFile(target, blob); await fs.chmod(target, 0o444);
      result.localFile = localFile;
    }
    if (!result.binary) {
      const text = blob.toString('utf8'), offset = options.offset || 0, end = options.maxChars === undefined ? text.length : offset + options.maxChars;
      result.content = text.slice(offset, end); result.totalChars = text.length;
      if (end < text.length) result.nextOffset = end;
    }
    return result;
  }
  async materializeArtifactFiles(metadata, selected) {
    const files = [...new Set(selected)];
    for (const file of files) {
      if (!metadata.relatedFiles.includes(file)) throw new Error('Select files from this artifact version');
      checkedPath(this.root, file);
    }
    if (!files.length) return {};
    const task = run('git', [...gitArgs, '-C', this.root, 'cat-file', '--batch', '-z'], { windowsHide: true, encoding: 'buffer', maxBuffer: 128 * 1024 ** 2 });
    task.child.stdin.end(files.map(file => metadata.revision + ':' + file).join('\0') + '\0');
    const bytes = (await task).stdout, blobs = [];
    let offset = 0;
    for (const file of files) {
      const end = bytes.indexOf(10, offset), header = bytes.toString('utf8', offset, end).match(/^[a-f0-9]+ blob (\d+)$/);
      if (!header) throw new Error('Cannot read saved artifact file: ' + file);
      const size = Number(header[1]);
      blobs.push(bytes.subarray(end + 1, end + 1 + size)); offset = end + size + 2;
    }
    await ensureProjectGit(this.root);
    return Object.fromEntries(await Promise.all(files.map(async (file, index) => {
      const localFile = '.highzyme/reference-files/' + metadata.revision + '/' + metadata.id + '/' + file;
      const target = checkedPath(this.root, localFile);
      await fs.mkdir(path.dirname(target), { recursive: true });
      if (existsSync(target)) await fs.chmod(target, 0o644);
      await fs.writeFile(target, blobs[index]); await fs.chmod(target, 0o444);
      return [file, target];
    })));
  }
  async jobs() {
    const folder = path.join(this.root, '.highzyme', 'jobs');
    const files = await fs.readdir(folder).catch(e => { if (e.code === 'ENOENT') return []; throw e; });
    return Promise.all(files.filter(f => f.endsWith('.json')).map(f => readJson(path.join(folder, f), {})));
  }
  async saveJob(job) {
    if (!/^[a-zA-Z0-9_-]+$/.test(job.id)) throw new Error('Invalid job ID');
    await writeJson(path.join(this.root, '.highzyme', 'jobs', job.id + '.json'), job);
  }
  async changedFiles() {
    await ensureProjectGit(this.root);
    const lists = await Promise.all([
      git(this.root, ['diff', 'HEAD', '--name-only']).catch(() => git(this.root, ['diff', '--cached', '--name-only'])),
      git(this.root, ['ls-files', '--modified', '--deleted', '--others', '--exclude-standard']),
    ]);
    return [...new Set(lists.join('\n').split('\n').filter(Boolean))];
  }
  async history() {
    const log = await git(this.root, ['log', '--format=%H%x1f%at%x1f%s%x1f%b%x1e']).catch(() => '');
    return log.split('\x1e').map(row => row.trim()).filter(Boolean).map(row => {
      const [revision, time, message, body = ''] = row.split('\x1f');
      return { revision, time: +time, message, sessionId: body.match(/^Highzyme-Session: (.+)$/m)?.[1], caseId: body.match(/^Highzyme-Case: (.+)$/m)?.[1] };
    });
  }
}

export function discussionTurns(messages) {
  const turns = [];
  for (const message of messages) {
    if (message.role === 'user') turns.push({ index: turns.length + 1, messages: [message] });
    else if (message.role === 'assistant' && turns.length) turns.at(-1).messages.push(message);
  }
  return turns;
}

export function selectDiscussion(messages, { rounds = 1, messageIds } = {}) {
  const turns = discussionTurns(messages);
  if (messageIds !== undefined) {
    if (!Array.isArray(messageIds) || !messageIds.length) throw new Error('Select discussion messages');
    const known = new Set(turns.flatMap(turn => turn.messages.map(m => m.id)));
    if (messageIds.some(id => !known.has(id))) throw new Error('Unknown discussion message');
    const selected = turns.filter(turn => turn.messages.some(m => messageIds.includes(m.id)));
    if (selected.length > 15) throw new Error('Select no more than 15 rounds');
    return selected.flatMap(turn => turn.messages.filter(m => messageIds.includes(m.id)));
  }
  if (!Number.isInteger(rounds) || rounds < 1 || rounds > 15) throw new Error('Choose 1 to 15 rounds');
  return turns.slice(-rounds).flatMap(turn => turn.messages);
}

export function parseArtifactDraft(output, messages) {
  const text = output.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  const draft = JSON.parse(text);
  if (!draft.title?.trim() || !draft.content?.trim() || !['source', 'plan', 'result'].includes(draft.kind) || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(draft.file_stem)) throw new Error('The draft needs a title, Markdown content, category and English keyword filename');
  const ids = new Set(messages.map(m => m.id));
  if (!Array.isArray(draft.source_message_ids) || draft.source_message_ids.some(id => !ids.has(id))) throw new Error('The draft contains unknown source messages');
  const sourceText = messages.map(m => m.text).join('\n');
  if (!Array.isArray(draft.source_references) || draft.source_references.some(ref => typeof ref !== 'string' || !sourceText.includes(ref))) throw new Error('The draft contains unknown source references');
  return { title: draft.title.trim(), fileStem: draft.file_stem, kind: draft.kind, content: draft.content, sourceMessageIds: draft.source_message_ids, sourceReferences: draft.source_references };
}

/** Additional grants narrow native permissions; they never upgrade the sandbox. */
export function deniedTool(project, execution, cwd, nativeMode = 'workspace-write') {
  if (execution.name === 'highzyme_case_research' && execution.arguments?.action !== 'read' && nativeMode === 'read-only') return 'This session is read-only.';
  if (execution.name === 'highzyme_dataset_save' && nativeMode === 'read-only') return 'This session is read-only.';
  const { name, arguments: args = {} } = execution;
  const access = project.access;
  const cleanup = ['interrupt_agent', 'cancel_agent', 'job_kill', 'terminal_close', 'terminal_signal'];
  if ((/^(bash|pwsh|shell|exec|terminal|workflow)/.test(name)) && !cleanup.includes(name) && !access.shell) return 'Local execution is off under this project access policy.';
  if (/^(web|search_web|fetch)/.test(name) && !access.network) return 'Network access is disabled for this project.';
  if (['highzyme_compute_submit', 'highzyme_qe_submit', 'highzyme_qe_test'].includes(name) && !access.compute) return 'Enable external computation in Settings after connecting your resource.';
  if (name === 'highzyme_compute_setup' && !access.network) return 'Network access is disabled for this project.';
  if (nativeMode === 'read-only' && (['highzyme_qe_prepare', 'highzyme_qe_workflow_prepare', 'highzyme_qe_submit', 'highzyme_qe_collect', 'highzyme_qe_test', 'highzyme_compute_submit'].includes(name) || name === 'highzyme_compute_setup' && !['inspect', 'check'].includes(args.action))) return 'This session is read-only.';
  if (nativeMode === 'read-only' && (['highzyme_artifact_save', 'highzyme_project_checkpoint', 'highzyme_compute_download', 'highzyme_compute_submit', 'highzyme_fit_kinetics', 'highzyme_replot_kinetics', 'highzyme_evidence_save', 'highzyme_compare_evidence', 'highzyme_analyze_signal', 'highzyme_simulate_reaction', 'highzyme_image_colorimetry', 'highzyme_replot_analysis', 'highzyme_render_document', 'highzyme_retrieve_publication', 'highzyme_delegate_research'].includes(name) || ['highzyme_formulation', 'highzyme_chemical_identity'].includes(name) && (args.output_prefix || args.artifact_id || args.new_analysis))) return 'This session is read-only.';
  if (name === 'highzyme_retrieve_publication' && !access.network) return 'Network access is disabled for this project.';
  if ((access.content === 'selected' || access.denyRead.length || access.denyWrite.length) && !name.startsWith('highzyme_') && ![...cleanup, 'skill', 'ask_user_question', 'todo_write', 'subagent', 'subagent_fork', 'list_agents', 'wait_agent', 'send_message', 'read', 'read_image', 'write', 'edit', 'web_search', 'web_fetch', 'exit_plan_mode'].includes(name)) return 'Selected-file access is active. Use highzyme_project_context and explicitly granted files.';
  if (['read', 'read_image', 'write', 'edit'].includes(name)) {
    const file = args.path || args.file_path;
    if (typeof file !== 'string') return 'A file path is required.';
    const target = path.resolve(cwd || project.root, file);
    if (name === 'read' && contains(bundledSkills, target)) return;
    if (!contains(project.root, target)) return access.content === 'selected' || nativeMode !== 'danger-full-access' ? 'File is outside the permitted project.' : undefined;
    const rel = path.relative(project.root, target).split(path.sep).join('/');
    try { checkedPath(project.root, rel); } catch { return 'File resolves outside the project.'; }
    if (!project.permitted(rel, ['write', 'edit'].includes(name) ? 'write' : 'read')) return 'This file is not granted for that operation. Update Agent access in the project panel.';
  }
}
