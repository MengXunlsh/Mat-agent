import { promises as fs } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { ComputeResources } from './state.mjs';
import { ResearchProject, DEFAULT_OPERATIONS, englishStem, discussionTurns, selectDiscussion, parseArtifactDraft, checkedPath, checkpoint, git, contains, deniedTool, projectContext } from './research.mjs';
import { readJson, writeJson } from './state.mjs';
import { science, scientificRuntime, runPython } from './science.mjs';
import { prepareRestore, restoreVersion, revisionFiles } from './versions.mjs';
import { ProjectMemory } from './memory.mjs';
import { Workareas } from './workareas.mjs';
import { projectEvidence } from './evidence.mjs';
import { fitProjectKinetics, replotProjectKinetics } from './kinetics.mjs';
import { registerCalculationTools } from './calculation-tools.mjs';
import { registerDocumentTools } from './document-tools.mjs';
import { delegateResearch } from './research-delegation.mjs';
import { analysisOptions, resultFileAction, projectScience } from './project-science.mjs';
import { registerArtifactTools } from './artifact-tools.mjs';
import { registerComputeTools, collectQE, updateComputeJob, reconcileComputeJobs } from './compute-tools.mjs';
import { artifactVisual, artifactMedia } from './result-views.mjs';
import { JOB_DEFAULTS } from './resource-policy.mjs';
import { DefaultModelSettings } from './default-model.mjs';
import { DatasetService, registerDatasetTools, saveDatasetRecord } from './dataset.mjs';
import { RESEARCH_WORKFLOWS, caseResearch, updateCaseResearch, researchValidations, registerCaseResearchTools } from './case-research.mjs';

const requireRuntime = createRequire(new URL('../web-runtime/package.json', import.meta.url));
const { defineTool } = await import(pathToFileURL(requireRuntime.resolve('@deepseek-ai/dsh-tools')).href);
const { Session } = await import(pathToFileURL(requireRuntime.resolve('@deepseek-ai/dsh-session')).href);
const home = path.resolve(process.env.DSH_HOME);
const here = path.dirname(fileURLToPath(import.meta.url));
export const name = 'highzyme-foundation';
export const inject = ['tools', 'connection', 'credentials', 'workspaceRegistry', 'sessions', 'sessionPersistence', 'workingDirectory', 'agents', 'systemPrompt', 'jobs', 'agentPresets', 'sessionController', 'agentDefaultModel', 'llm'];

export async function apply(ctx) {
  const defaultModel = new DefaultModelSettings(ctx);
  const dataset = new DatasetService(home);
  await dataset.load();
  ctx.effect(() => () => dataset.dispose());
  const projects = new Map(), pending = new Map(), restrictions = new Map(), drafts = new Map(), organizers = new Set(), resources = new ComputeResources(home, ctx.credentials);
  await resources.load();
  const operationsFile = path.join(home, 'operations.json');
  const savedOperations = await readJson(operationsFile, {});
  const operations = Object.fromEntries(Object.entries(DEFAULT_OPERATIONS).map(([key, value]) => [key, savedOperations[key] ?? value]));
  const editorPrompt = await fs.readFile(path.join(here, 'artifact-editor.txt'), 'utf8');
  const childPrompt = await fs.readFile(path.join(here, 'subagent-persona.txt'), 'utf8');
  const memories = new Map(), workareas = new Map();
  async function project(id) {
    const workspace = ctx.workspaceRegistry.list().find(w => w.id === id);
    if (!workspace) throw new Error('Project is not open');
    if (!projects.has(id)) {
      if (!pending.has(id)) pending.set(id, new ResearchProject(workspace, operations).load().then(async p => { projects.set(id, p); memories.set(id, new ProjectMemory(ctx, p.root, () => { for (const agent of ctx.agents.list()) updateTools(agent); })); await memories.get(id).config(); workareas.set(id, await new Workareas(p, ctx.workingDirectory).load()); for (const row of workareas.get(id).rows) if (row.active) await workareas.get(id).view(row.sessionId); pending.delete(id); return p; }));
      return pending.get(id);
    }
    return projects.get(id);
  }
  const workspaceFor = session => ctx.workspaceRegistry.list().filter(w => contains(w.path, session?.header.cwd || '')).sort((a, b) => b.path.length - a.path.length)[0];
  const ownerSession = session => session?.header.origin === 'subagent' && ctx.sessions.get(session.header.parentSession) ? ownerSession(ctx.sessions.get(session.header.parentSession)) : session;
  const baseProject = session => projects.get(workspaceFor(session)?.id);
  const liveProject = session => workareas.get(workspaceFor(session)?.id)?.current(ownerSession(session)?.id);
  const ownerFor = (p, session) => { const owner = ownerSession(session); return { sessionId: owner?.id || null, caseId: p.caseFor(owner)?.id || null }; };
  const requireProject = async exec => {
    const w = workspaceFor(exec.agent?.session); if (!w) throw new Error('Open a local project first');
    await project(w.id); return workareas.get(w.id).view(ownerSession(exec.agent.session).id);
  };

  async function readSession(p, id) {
    if (!ctx.workspaceRegistry.list().find(w => w.id === p.id).sessionIds.includes(id)) throw new Error('Choose a conversation in this project');
    const live = ctx.sessions.get(id); if (live) return live;
    const handle = await ctx.sessionPersistence.open(id, 'read');
    try { const seed = await handle.read(); return Session.fromRestore(id, seed.events, handle.header, handle.inheritedEventCount, seed.eventState, ctx.sessions.messageProjections); }
    finally { await handle.close(); }
  }
  const discussionMessages = session => session.log.filter(e => e.type === 'user/message' && e.data.source.kind === 'user' || e.type === 'assistant/message').map(e => e.type === 'user/message' ? e.data : e.data.message).map(m => ({ id: m.id, role: m.role, text: m.content.filter(b => b.type === 'text').map(b => b.text).join('\n') })).filter(m => m.text);
  const nativeMode = agent => agent?.ctx.get('sandboxPolicy')?.resolve({ session: agent.session }).mode || 'workspace-write';
  const updateTools = agent => {
    restrictions.get(agent.session.id)?.();
    const p = liveProject(agent.session);
    const deny = p?.access.compute && resources.list().some(r => r.enabled) ? [] : ['highzyme_compute_submit', 'highzyme_qe_submit', 'highzyme_qe_test'];
    if (!dataset.registry) deny.push('highzyme_dataset_catalog', 'highzyme_dataset_material', 'highzyme_dataset_search', 'highzyme_dataset_read', 'highzyme_dataset_save', 'highzyme_material_space');
    else if (!dataset.analysisRegistry) deny.push('highzyme_material_space');
    if (p && (p.access.content === 'selected' || p.access.denyRead.length || p.access.denyWrite.length)) deny.push('bash', 'pwsh', 'glob', 'grep', 'present');
    if (p && !p.access.shell) deny.push('bash', 'pwsh');
    if (p && !p.access.network) deny.push('web_search', 'web_fetch', 'highzyme_retrieve_publication');
    for (const memory of memories.values()) for (const operation of ['create_entities', 'create_relations', 'add_observations', 'delete_entities', 'delete_observations', 'delete_relations', 'read_graph', 'search_nodes', 'open_nodes']) deny.push('mcp__' + memory.namespace + '__' + operation);
    if (!memories.get(p?.id)?.enabled || p.access.content !== 'project' || p.access.denyRead.length) deny.push('highzyme_memory_search', 'highzyme_memory_save', 'highzyme_memory_delete');
    restrictions.set(agent.session.id, agent.ctx.tools.restrict({ deny: deny.filter(name => ctx.tools.get(name, agent)), ...(organizers.has(agent.session.id) ? { allow: ['read', 'read_image', 'highzyme_read_document', 'highzyme_read_structure', 'highzyme_project_context', 'highzyme_artifact_read'] } : {}) }));
  };
  const caseContext = (p, session) => {
    const c = p.caseFor(ownerSession(session));
    return projectContext(p, c, { localShell: p.access.shell, memoryEnabled: memories.get(p.id)?.enabled || false,
      scientificRuntime,
      dataset: { connected: !!dataset.registry, materialSpace: !!dataset.registry && !!dataset.analysisRegistry },
      researchWorkflow: { kind: c?.research?.kind || 'general', stage: c?.research?.stage || 'objective', file: c?.research?.file || null, skill: RESEARCH_WORKFLOWS[c?.research?.kind || 'general']?.skill || null },
      artifactDirectory: c ? c.folder + '/artifacts' : p.data.artifactFolders?.[ownerSession(session)?.id] ? 'artifacts/' + p.data.artifactFolders[ownerSession(session).id] : 'artifacts/<english-discussion-keywords>',
      compute: resources.list().filter(r => r.enabled && p.access.compute).map(r => ({ id: r.id, name: r.name, capabilities: r.probe?.capabilities || [] })) });
  };
  for (const workspace of ctx.workspaceRegistry.list()) await project(workspace.id);
  ctx.on('agent/created', async ({ agent }) => {
    const w = workspaceFor(agent.session); if (!w) return;
    const p = await project(w.id), c = p.caseFor(ownerSession(agent.session));
    const area = workareas.get(w.id)?.row(ownerSession(agent.session).id);
    if (area?.active) await ctx.workingDirectory.set(agent, area.path);
    else await ctx.workingDirectory.set(agent, p.root);
    updateTools(agent);
  });
  ctx.effect(() => ctx.tools.guard(exec => {
    if (!exec.agent) return;
    if (exec.name.startsWith('mcp__hzmem_')) return 'Use the project memory tools.';
    if (organizers.has(exec.agent.session.id) && !['read', 'read_image', 'highzyme_read_document', 'highzyme_read_structure', 'highzyme_project_context', 'highzyme_artifact_read'].includes(exec.name)) return 'This task only organizes the selected discussion and authorized sources.';
    const p = liveProject(exec.agent.session);
    if (!p) {
      if (['highzyme_compute_resources', 'highzyme_compute_setup'].includes(exec.name)) return deniedTool({ access: { content: 'project', denyRead: [], denyWrite: [], ...operations } }, exec, '', nativeMode(exec.agent));
      if (['skill', 'ask_user_question'].includes(exec.name)) return;
      return 'Open a local project first.';
    }
    const c = p.caseFor(ownerSession(exec.agent.session));
    if (c && c.status !== 'active') return 'Restore this case before continuing work.';
    return deniedTool(p, exec, ctx.workingDirectory.get(exec.agent.session), nativeMode(exec.agent));
  }));
  ctx.systemPrompt.context({ name: 'highzyme:subagent', order: 310, required: true, interpolate: false, text: ({ agent }) => agent?.session.header.origin === 'subagent' ? childPrompt : '' });
  ctx.systemPrompt.context({ name: 'highzyme:project', order: 320, required: true, interpolate: false,
    text: ({ agent }) => {
      const p = agent && liveProject(agent.session); if (!p) return '';
      const context = caseContext(p, agent.session);
      return 'mat-agent project context: ' + JSON.stringify(context);
    } });

  const tool = (name, description, parameters, execute) => ctx.tools.register(defineTool({ name, description, parameters,
    output: { schema: { type: 'object', additionalProperties: true }, render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] }, execute }));
  registerCalculationTools({ tool, requireProject, ownerFor });
  registerDocumentTools({ tool, requireProject, ownerFor });
  registerDatasetTools({ tool, requireProject, ownerFor, dataset });
  registerCaseResearchTools({ tool, requireProject, ownerFor, caseFor: (p, session) => p.caseFor(ownerSession(session)) });
  registerArtifactTools({ tool, requireProject, ownerFor, caseFor: (p, session) => p.caseFor(ownerSession(session)) });
  tool('highzyme_delegate_research', 'Assign a bounded literature extraction, data analysis or evidence review to a native Harness subagent. Use for substantial independent work, not simple calculations. The child inherits the current model and project permissions. Returns a task ID; use highzyme_research_task to wait for or cancel it.', {
    role: { type: 'string', required: true, enum: ['literature', 'analysis', 'verification'] },
    goal: { type: 'string', required: true }, files: { type: 'array', required: true, items: { type: 'string' } },
    output_file: { type: 'string' }, artifact_id: { type: 'string', description: 'Existing report artifact to revise; omit for an independent assignment' }, language: { type: 'string', enum: ['zh', 'en'] },
  }, async (args, exec) => {
    const p = await requireProject(exec);
    return delegateResearch({ ctx, project: p, parent: exec.agent, args, owner: ownerFor(p, exec.agent.session), activations: drafts });
  });
  tool('highzyme_research_task', 'Wait for or cancel a recorded research subagent. Waits up to 30 seconds by default; use wait_ms=0 only for an immediate status check. Do not read the expected output before the job completes. Completed non-literature reports are already published.', {
    job_id: { type: 'string', required: true }, action: { type: 'string', enum: ['status', 'cancel'] }, wait_ms: { type: 'integer' },
  }, async (args, exec) => {
    const p = await requireProject(exec);
    const activation = drafts.get(args.job_id);
    const wait = args.wait_ms ?? 30000, started = Date.now();
    if (activation && args.action !== 'cancel' && wait) await Promise.race([activation.result.catch(() => {}), new Promise(resolve => setTimeout(resolve, Math.min(30000, Math.max(0, wait))))]);
    return { ...await jobUpdate(p, args.job_id, args.action || 'status', exec.signal), waited_ms: Date.now() - started, wait_limit_ms: 30000 };
  });
  tool('highzyme_project_context', 'Read the current project, optional research case, artifact references and access grants.', {}, async (_args, exec) => caseContext(await requireProject(exec), exec.agent.session));
  for (const action of ['search', 'save', 'delete']) tool('highzyme_memory_' + action,
    'Use enabled local project memory for accepted decisions, preferences and reusable methods. Keep scientific reports in artifacts. Search before saving to update existing notes.',
    action === 'search' ? { query: { type: 'string', required: true } } : action === 'delete' ? { id: { type: 'string', required: true } } : { id: { type: 'string' }, title: { type: 'string', required: true }, content: { type: 'string', required: true } }, async (args, exec) => {
      const p = baseProject(exec.agent.session), memory = memories.get(p.id);
      if (!(await memory.config()).enabled) throw new Error('Enable project memory in the project panel first');
      if (p.access.content !== 'project' || p.access.denyRead.length) throw new Error('Project memory is unavailable while source access is restricted');
      if (action !== 'search' && nativeMode(exec.agent) === 'read-only') throw new Error('This session is read-only');
      return { memories: action === 'search' ? await memory.list(args.query) : action === 'save' ? await memory.save(args, ownerFor(p, exec.agent.session)) : await memory.remove(args.id) };
    });
  tool('highzyme_chemical_identity', 'Parse an explicit chemical formula or SMILES using RDKit. Omit output_prefix for a numeric answer; provide it to save a project artifact with a molecular depiction or composition table. No remote API or computation resource is required.', {
    formula: { type: 'string' }, smiles: { type: 'string' }, ...analysisOptions, language: { type: 'string', enum: ['zh', 'en'] },
  }, async (args, exec) => {
    if (!!args.formula === !!args.smiles) throw new Error('Supply one formula or SMILES');
    if (args.output_prefix || args.artifact_id || args.new_analysis) {
      const p = await requireProject(exec);
      return projectScience(p, args, ownerFor(p, exec.agent.session), { action: 'identity', stem: 'chemical-identity', title: args.language === 'zh' ? '化学身份核对' : 'Chemical identity',
        suffixes: ['-result.json', '-input.json', '-report.md', '-reproduce.py', '-structure.svg'] }, exec.signal);
    }
    return science({ action: 'identity', ...args }, exec.signal);
  });
  tool('highzyme_inspect_table', 'Preview CSV, TSV or XLSX column names and up to eight rows without loading the full table. Row count is null when more data exists. For multi-sheet XLSX select a sheet before analysis.', {
    file: { type: 'string', required: true }, sheet: { type: 'string' },
  }, async (args, exec) => {
    const p = await requireProject(exec);
    if (!p.permitted(args.file)) throw new Error('Grant Agent access to the table first');
    return science({ ...args, action: 'inspect_table', file: checkedPath(p.root, args.file) }, exec.signal);
  });
  tool('highzyme_fit_kinetics', 'Fit supplied substrate concentration and initial-rate columns to Michaelis-Menten kinetics using nonlinear least squares. Saves data, report, JSON, PNG/SVG and reproduction script in the current project/case and records a Git version. Requires file write permission; no external compute. Units are preserved.', {
    file: { type: 'string', required: true, description: 'Project-relative CSV, TSV or XLSX input' },
    concentration_column: { type: 'string', required: true }, rate_column: { type: 'string', required: true },
    concentration_unit: { type: 'string', required: true }, rate_unit: { type: 'string', required: true },
    sheet: { type: 'string' }, sigma_column: { type: 'string', description: 'Optional known rate standard deviations, not replicate counts' },
    group_columns: { type: 'array', items: { type: 'string' }, description: 'Fit each distinct combination separately, at most 12 groups' },
    context_columns: { type: 'array', items: { type: 'string' }, description: 'Conditions required to be constant within each group' },
    plot_layout: { type: 'string', enum: ['overlay', 'panels'] },
    assay_context: { type: 'string', description: 'User-supplied material, substrate and assay conditions' },
    language: { type: 'string', enum: ['zh', 'en'] },
    ...analysisOptions,
  }, async (args, exec) => {
    const p = await requireProject(exec);
    return fitProjectKinetics(p, args, ownerFor(p, exec.agent.session), exec.signal);
  });
  tool('highzyme_replot_kinetics', 'Redraw a saved kinetics result without refitting or changing numerical data. Choose overlay/panels and one label per group. Plot options and graphics are versioned.', {
    file: { type: 'string', required: true, description: 'Project-relative saved -result.json' },
    plot_layout: { type: 'string', enum: ['overlay', 'panels'] }, labels: { type: 'array', items: { type: 'string' } },
    ...analysisOptions, language: { type: 'string', enum: ['zh', 'en'] },
  }, async (args, exec) => {
    const p = await requireProject(exec);
    return replotProjectKinetics(p, args, ownerFor(p, exec.agent.session), exec.signal);
  });
  tool('highzyme_evidence_save', 'Validate and publish a highzyme.evidence.v1 JSON draft following the literature-evidence skill. Checks material/assay references, source locators and verbatim quotes, then saves JSON, CSV, Markdown and a Git version. Interpretation remains declared review status. Use artifact_id for a revision and a separate input draft.', {
    file: { type: 'string', required: true, description: 'Project-relative evidence JSON draft' },
    ...analysisOptions, language: { type: 'string', enum: ['zh', 'en'] },
  }, async (args, exec) => {
    const p = await requireProject(exec);
    return projectEvidence(p, args, ownerFor(p, exec.agent.session), 'save_evidence', exec.signal);
  });
  tool('highzyme_compare_evidence', 'Compare 2 to 12 assays from saved evidence datasets. Preserve raw values and sources, convert compatible units for field comparison, list differences, missing or unreviewed evidence. No performance ranking. Use the assay-comparison skill.', {
    selections: { type: 'array', required: true, items: { type: 'object', additionalProperties: false, properties: { file: { type: 'string', required: true }, assay_ids: { type: 'array', required: true, items: { type: 'string' } } } } },
    purpose: { type: 'string', enum: ['overview', 'material_activity', 'condition_effect'] },
    fields: { type: 'array', items: { type: 'string' } }, varied_field: { type: 'string' }, question: { type: 'string' },
    ...analysisOptions, language: { type: 'string', enum: ['zh', 'en'] },
  }, async (args, exec) => {
    const p = await requireProject(exec);
    return projectEvidence(p, args, ownerFor(p, exec.agent.session), 'compare_evidence', exec.signal);
  });
  for (const kind of ['structure', 'document']) tool('highzyme_read_' + kind,
    kind === 'structure' ? 'Read project MOL/SDF/CIF/mmCIF/PDB/XYZ/EXTXYZ/VASP/POSCAR/CONTCAR structures using RDKit, Gemmi or ASE.' : 'Read project PDF pages or DOCX text blocks with source locators. Use native read for plain text and native read_image for images.', {
      file: { type: 'string', required: true, description: 'Project-relative source path' }, start: { type: 'integer' }, end: { type: 'integer' },
    }, async (args, exec) => {
      const p = await requireProject(exec), file = checkedPath(p.root, args.file);
      if (!p.permitted(args.file)) throw new Error('Grant Agent access to this source file first');
      const extensions = kind === 'structure' ? ['.mol', '.sdf', '.cif', '.mmcif', '.pdb', '.xyz', '.extxyz', '.vasp', '.poscar', '.contcar'] : ['.pdf', '.docx'];
      if (!extensions.includes(path.extname(file).toLowerCase()) && !(kind === 'structure' && ['POSCAR', 'CONTCAR'].includes(path.basename(file).toUpperCase()))) throw new Error('Supported files: ' + extensions.join(', '));
      return science({ ...args, action: kind, file, root: p.root }, exec.signal);
    });
  tool('highzyme_project_checkpoint', 'Record a meaningful completed task or adopted change using project Git. Does not commit when there is no file change.', {
    message: { type: 'string', required: true },
    paths: { type: 'array', items: { type: 'string' }, required: true, description: 'Only the project-relative files changed for this task' },
  }, async (args, exec) => {
    const p = await requireProject(exec);
    if (!args.paths.length || args.paths.some(file => !p.permitted(file, 'write'))) throw new Error('Select authorized files changed for this task');
    return p.mutate(() => checkpoint(p.root, args.message, args.paths, ownerFor(p, exec.agent.session)));
  });

  // Reuse the native job registry for execution and persist research job identity
  // for the project-level task view. Restart never resubmits a remote request.
  ctx.on('session/event', (session, event) => {
    if (event.type === 'session/title') {
      const p = liveProject(session), c = p?.caseFor(session);
      if (c && c.title !== event.data.title) p.mutate(() => p.updateCase(c.id, { title: event.data.title })).catch(error => console.error(error.message));
    }
    if (!['job/registered', 'job/settled'].includes(event.type)) return;
    const p = liveProject(session); if (!p) return;
    p.mutate(async () => {
      const current = (await p.jobs()).find(j => j.id === event.data.jobId) || {};
      await p.saveJob({ ...current, ...event.data, id: event.data.jobId, sessionId: session.id, type: 'native', status: event.type === 'job/registered' ? 'running' : event.data.status });
    }).catch(error => console.error('mat-agent task record:', error.message));
  });
  async function jobUpdate(p, id, action, signal) {
    const record = (await p.jobs()).find(j => j.id === id);
    if (!record) throw new Error('Task not found');
    if (record.type === 'organize' || record.type === 'research') {
      if (action === 'cancel' && drafts.has(id)) { const activation = drafts.get(id); activation.userCancelled = true; await activation.dispose(); }
      const stored = (await p.jobs()).find(j => j.id === id);
      return !drafts.has(id) && ['running', 'queued'].includes(stored.status) ? { ...stored, status: 'interrupted' } : stored;
    }
    if (record.type === 'native') {
      if (action === 'cancel') ctx.jobs.kill(id, record.sessionId, 'Cancelled by user');
      try { return ctx.jobs.get(id, record.sessionId); } catch { return { ...record, status: ['running', 'queued'].includes(record.status) ? 'interrupted' : record.status }; }
    }
    return updateComputeJob(p, resources, id, action, signal);
  }
  async function setupResource(action, input) {
    let result;
    if (action === 'inspect') {
      const profile = await runPython('highzyme.compute.ssh_slurm', { action: 'validate', profile: input });
      result = await runPython('highzyme.compute.ssh_slurm', { action: 'probe', profile, state: path.join(home, 'compute-jobs') });
    } else if (action === 'save') result = await resources.configure(input);
    else if (action === 'check') result = await resources.probe(input.id);
    else if (action === 'enable' || action === 'disable') result = await resources.enable(input.id, action === 'enable');
    else throw new Error('Unknown setup action');
    for (const agent of ctx.agents.list()) updateTools(agent);
    return result;
  }
  const computeTools = registerComputeTools({ tool, requireProject, ownerFor, resources, jobUpdate, setupResource, setupPermission: exec => liveProject(exec.agent?.session)?.access.compute ?? operations.compute });
  let checkingCompute = false;
  const computeTimer = setInterval(async () => {
    if (checkingCompute) return;
    checkingCompute = true;
    try {
      for (const p of projects.values()) await reconcileComputeJobs(p, resources);
    } finally { checkingCompute = false; }
  }, 15000);
  computeTimer.unref(); ctx.effect(() => () => clearInterval(computeTimer));

  async function projectJobs(p, sessions) {
    const storedJobs = await p.jobs();
    const live = sessions.flatMap(s => ctx.jobs.list(s).filter(j => j.owner === s).map(j => ({ ...storedJobs.find(record => record.id === j.id), ...j, sessionId: s, type: 'native' })));
    const liveIds = new Set(live.map(j => j.id));
    const stored = storedJobs.filter(j => !liveIds.has(j.id)).map(({ content, summary, ...j }) => ({ ...j, status: (j.type === 'native' || ['organize', 'research'].includes(j.type) && !drafts.has(j.id)) && ['running', 'queued'].includes(j.status) ? 'interrupted' : j.status, needsRefresh: j.type === 'compute' && ['running', 'queued'].includes(j.status) }));
    return [...live, ...stored];
  }
  async function detail(id, sessionId) {
    const base = await project(id), p = await workareas.get(id).view(sessionId), sessions = ctx.workspaceRegistry.list().find(w => w.id === id).sessionIds;
    for (const c of p.data.cases) {
      if (!c.sessions.length) continue;
      const archived = c.sessions.every(id => ctx.workspaceRegistry.archivedSessionIds.includes(id));
      if (c.status === 'active' && archived) await p.mutate(() => p.updateCase(c.id, { status: 'archived' }));
      if (c.status !== 'active' && !archived) await p.mutate(() => p.updateCase(c.id, { status: 'active' }));
    }
    const jobs = await projectJobs(p, sessions);
    const owner = sessionId ? ownerFor(p, await readSession(base, sessionId)) : {};
    const history = (await p.history()).filter(r => owner.caseId ? r.caseId === owner.caseId || p.case(owner.caseId).sessions.includes(r.sessionId) : r.sessionId === sessionId);
    const listed = (await ctx.get('sessionController').list({})).items;
    const archives = base.data.cases.filter(c => c.status !== 'active').map(c => ({ id: c.id, title: c.title, kind: 'case', status: c.status, time: c.updatedAt || c.createdAt, folder: c.folder }));
    for (const sid of sessions) if (!base.data.cases.some(c => c.sessions.includes(sid)) && ctx.workspaceRegistry.archivedSessionIds.includes(sid)) archives.push({ id: sid, title: listed.find(s => s.sessionId === sid)?.projections?.values?.title || sid, kind: 'session', status: base.data.sessionStates?.[sid]?.status || 'archived', time: base.data.sessionStates?.[sid]?.time || null });
    return { id, path: p.root, ...p.data, datasetConnected: !!dataset.registry, access: p.access, jobs, history, archives, sessionTitles: Object.fromEntries(listed.filter(s => sessions.includes(s.sessionId)).map(s => [s.sessionId, s.projections?.values?.title || ''])), memory: await memories.get(id).config(), workarea: workareas.get(id).row(sessionId) || null };
  }
  async function api(request) {
    const { action = 'state', ...input } = request.method === 'POST' ? await request.json() : {};
    if (action === 'dataset.config') return { registry: dataset.registry, analysisRegistry: dataset.analysisRegistry };
    if (action === 'dataset.choose') return runPython('highzyme.foundation_science', { action: 'choose_file', kind: 'dataset' });
    if (action === 'dataset.connect') {
      const result = await dataset.configure(input.registry, input.analysisRegistry);
      for (const agent of ctx.agents.list()) updateTools(agent);
      return result;
    }
    if (['dataset.catalog', 'dataset.search', 'dataset.read'].includes(action)) return dataset.request(action.slice(8), action === 'dataset.read' ? { ...input, detail: input.detail || 'full' } : input);
    if (action === 'dataset.save') {
      const p = await project(input.projectId);
      const session = await readSession(p, input.sessionId);
      return saveDatasetRecord(await workareas.get(p.id).view(session.id), dataset, input.selection_id, ownerFor(p, session), input.title);
    }
    if (action === 'state') return { version: 4, operations, jobDefaults: JOB_DEFAULTS, projects: ctx.workspaceRegistry.list().map(w => ({ id: w.id, name: w.title, path: w.path, sessions: w.sessionIds, cases: projects.get(w.id)?.data.cases || [] })), resources: resources.list() };
    if (action === 'model.catalog') return defaultModel.catalog();
    if (action === 'model.default') return defaultModel.save(input);
    if (action === 'operations.save') {
      if (input.compute && !resources.list().some(r => r.enabled)) throw new Error('Connect and enable a compute resource first');
      Object.assign(operations, { shell: !!input.shell, network: !!input.network, compute: !!input.compute });
      await writeJson(operationsFile, operations);
      for (const agent of ctx.agents.list()) updateTools(agent);
      return operations;
    }
    if (action === 'project.open') {
      const workspace = await ctx.workspaceRegistry.create(input.path);
      await project(workspace.id); return { id: workspace.id, path: workspace.path };
    }
    if (action.startsWith('resource.')) {
      let result;
      if (action === 'resource.assistant') {
        const row = input.id ? resources.get(input.id) : await readJson(path.join(home, 'compute-setup.json'), {});
        if (input.setupSessionId) {
          row.setupSessionId = input.setupSessionId;
          if (input.id) await resources.persist();
          else await writeJson(path.join(home, 'compute-setup.json'), row);
        }
        return { sessionId: row.setupSessionId || null };
      }
      if (action === 'resource.inspect') result = await setupResource('inspect', input);
      else if (action === 'resource.choose-key') result = await runPython('highzyme.compute.ssh_slurm', { action: 'choose_key' });
      else if (action === 'resource.save') result = await resources.configure(input);
      else if (action === 'resource.probe') result = await resources.probe(input.id);
      else if (action === 'resource.enable') result = await resources.enable(input.id, input.enabled);
      else if (action === 'resource.remove') { await resources.remove(input.id); result = { removed: true }; }
      else throw new Error('Unknown resource operation');
      for (const agent of ctx.agents.list()) updateTools(agent);
      return result;
    }
    if (action === 'structure.visual') return science({ action: 'structure_view', text: input.text, name: input.name });
    const base = await project(input.projectId);
    const p = action.startsWith('project.') || action.startsWith('artifact.') || action.startsWith('case.research') ? await workareas.get(base.id).view(input.sessionId) : base;
    if (action === 'project.detail') return detail(p.id, input.sessionId);
    if (action === 'project.tasks') return { jobs: await projectJobs(p, ctx.workspaceRegistry.list().find(w => w.id === p.id).sessionIds) };
    if (action === 'project.compute-test' || action === 'project.submit-qe') {
      const session = await readSession(base, input.sessionId);
      const resolved = await ctx.get('sessionController').resolveAgent(session.id);
      if (resolved.error) throw new Error(resolved.error.message);
      if (nativeMode(resolved.agent) === 'read-only') throw new Error('This session is read-only');
      if (action === 'project.submit-qe') return computeTools.submitQE(p, input.jobId);
      return computeTools.testQE(p, input.resourceId, ownerFor(p, session), input.language);
    }
    if (action.startsWith('memory.')) {
      const memory = memories.get(p.id);
      if (action === 'memory.enable') return memory.enable(input.enabled);
      if (action === 'memory.list') return memory.list(input.query);
      if (action === 'memory.save') return p.mutate(() => memory.save(input, { sessionId: input.sessionId || null }));
      if (action === 'memory.delete') return p.mutate(() => memory.remove(input.id));
    }
    if (action.startsWith('workarea.')) {
      const session = await readSession(base, input.sessionId);
      const activity = await ctx.waterfall('workspace/session-activity', { sessionId: session.id }, () => Promise.resolve([]));
      if (activity.length) throw new Error('Wait for the current task to finish');
      const resolved = await ctx.get('sessionController').resolveAgent(session.id);
      if (resolved.error) throw new Error(resolved.error.message);
      const areas = workareas.get(base.id), agent = resolved.agent;
      if (action === 'workarea.create') {
        if (!base.access.shell || nativeMode(agent) === 'read-only') throw new Error('Enable project writes and local execution first');
        return areas.create(agent, input.name, ctx.agentPresets.serviceFor(agent, 'worktrees'));
      }
      if (action === 'workarea.compare') return areas.compare(session.id);
      if (action === 'workarea.switch') return areas.activate(agent, input.active);
      if (action === 'workarea.merge') return base.mutate(() => areas.merge(session.id, ownerFor(base, session)));
      if (action === 'workarea.remove') return areas.remove(agent);
    }
    if (action === 'archive.update' || action === 'archive.delete') {
      const c = input.kind === 'case' ? base.case(input.id) : null;
      const ids = c ? c.sessions : [input.id];
      const workspace = ctx.workspaceRegistry.get(base.id);
      if (ids.some(id => !workspace.sessionIds.includes(id))) throw new Error('Choose a conversation in this project');
      if (action === 'archive.delete' && (c ? c.status !== 'trash' : base.data.sessionStates?.[input.id]?.status !== 'trash')) throw new Error('Move the item to trash first');
      for (const id of ids) {
        if ((await ctx.waterfall('workspace/session-activity', { sessionId: id }, () => Promise.resolve([]))).length) throw new Error('Stop running tasks before deleting or archiving');
        if (workareas.get(base.id).row(id)) throw new Error('Remove the independent workspace before deleting or archiving');
      }
      if (action === 'archive.update') {
        if (!['active', 'archived', 'trash'].includes(input.status)) throw new Error('Invalid archive state');
        for (const id of ids) await ctx.workspaceRegistry[input.status === 'active' ? 'unarchiveSession' : 'archiveSession'](id);
        if (c) await base.mutate(() => base.updateCase(c.id, { status: input.status }));
        else { base.data.sessionStates ||= {}; base.data.sessionStates[input.id] = { status: input.status, time: Date.now() }; await base.save(); }
        return { updated: true };
      }
      if (input.deleteFiles && c && base.data.cases.some(other => other.id !== c.id && other.references.some(r => (r.relatedFiles || [r.file]).some(file => file.startsWith(c.folder + '/'))))) throw new Error('Other cases reference files in this folder. Keep the files or remove those references first');
      const stored = await ctx.sessionPersistence.list();
      const allIds = new Set(ids);
      for (let changed = true; changed;) { changed = false; for (const row of stored) if (row.header.origin === 'subagent' && allIds.has(row.header.parentSession) && !allIds.has(row.header.id)) { allIds.add(row.header.id); changed = true; } }
      for (const id of [...allIds].reverse()) {
        await ctx.get('sessionController').agents.highzymeDispose(id);
        await ctx.get('sessionProjectionCache')?.highzymeDelete(id);
        await ctx.sessionPersistence.highzymeDelete(id);
        await workspace.detachSession(id);
        await ctx.workspaceRegistry.unarchiveSession(id);
      }
      for (const job of await base.jobs()) if (allIds.has(job.sessionId) || c && job.caseId === c.id) await fs.rm(checkedPath(base.root, '.highzyme/jobs/' + job.id + '.json'), { force: true });
      if (input.deleteFiles && c) { const folder = checkedPath(base.root, c.folder); if (!contains(base.root, folder) || folder === base.root) throw new Error('Invalid case folder'); await fs.rm(folder, { recursive: true, force: true }); base.data.artifacts = base.data.artifacts.filter(a => !a.file.startsWith(c.folder + '/')); }
      if (c) base.data.cases = base.data.cases.filter(row => row.id !== c.id);
      for (const id of allIds) if (base.data.sessionStates) delete base.data.sessionStates[id];
      await base.save(); return { deleted: [...allIds] };
    }
    if (action === 'case.research' || action === 'case.research.save') {
      const session = await readSession(p, input.sessionId);
      const c = input.caseId ? p.case(input.caseId) : p.caseFor(session);
      if (action === 'case.research') return { workflows: RESEARCH_WORKFLOWS, case: c, research: await caseResearch(p, c), validations: await researchValidations(p, c) };
      return updateCaseResearch(p, c, { ...input, action: input.operation || 'configure' }, ownerFor(p, session));
    }
    if (action === 'case.create') return p.mutate(async () => {
      if (input.workflowKind && !RESEARCH_WORKFLOWS[input.workflowKind]) throw new Error('Unknown case research workflow');
      const c = await p.createCase(input.title, input.folderName);
      if (input.workflowKind && input.workflowKind !== 'general') { c.research = { kind: input.workflowKind, stage: 'objective' }; await p.save(); }
      return c;
    });
    if (action === 'case.update') {
      const c = p.case(input.caseId);
      if (input.status && input.status !== 'active') for (const sessionId of c.sessions) {
        const activity = await ctx.waterfall('workspace/session-activity', { sessionId }, () => Promise.resolve([]));
        if (activity.length) throw new Error('Stop running case tasks before archiving or deleting');
      }
      const result = await p.mutate(() => p.updateCase(input.caseId, input));
      for (const id of c.sessions) {
        if (input.title) {
          await ctx.get('sessionController').rename({ sessionId: id, title: c.title });
        }
        if (input.status === 'active') await ctx.workspaceRegistry.unarchiveSession(id);
        else if (input.status) await ctx.workspaceRegistry.archiveSession(id);
      }
      return result;
    }
    if (action === 'case.attach') {
      const session = ctx.sessions.get(input.sessionId);
      if (!session || workspaceFor(session)?.id !== p.id) throw new Error('Choose a conversation in this project');
      const c = await p.mutate(() => p.attachSession(input.caseId, session.id));
      const agent = ctx.agents.get(session.id); if (agent) await ctx.workingDirectory.set(agent, p.root);
      ctx.get('sessionTitle')?.rename(session, c.title); return c;
    }
    if (action === 'artifact.save' || action === 'artifact.path') {
      const existing = p.data.artifacts.find(a => a.id === (input.artifactId || input.id) || a.file === input.file);
      const source = !existing && input.sessionId ? await readSession(p, input.sessionId) : null;
      const actor = input.currentSessionId ? await readSession(p, input.currentSessionId) : source;
      const values = { ...input, artifactId: existing?.id, sessionId: existing?.sessionId || input.sessionId,
        caseId: existing ? existing.caseId : p.caseFor(source)?.id || input.caseId || null, checkpointOwner: ownerFor(p, actor) };
      return p.mutate(async () => {
        if (action === 'artifact.path') return { file: await p.artifactPath(values) };
        const artifact = await p.publish(values);
        if (input.draftJobId) {
          const job = (await p.jobs()).find(j => j.id === input.draftJobId && j.type === 'organize');
          if (job) await p.saveJob({ ...job, savedArtifactId: artifact.id });
        }
        return artifact;
      });
    }
    if (action === 'artifact.reference') return p.mutate(() => p.reference(input.caseId, input.artifactId));
    if (action === 'artifact.read') return p.readArtifact(input.artifactId, input.caseId, false, { file: input.file, metadataOnly: input.metadataOnly });
    if (action === 'artifact.visual') return artifactVisual(p, input);
    if (action === 'artifact.media') return artifactMedia(p, input);
    if (action === 'artifact.file') {
      const result = await p.readArtifact(input.artifactId, input.caseId, false, { file: input.file, materialize: true, maxChars: 1 });
      return { file: result.localFile, revision: result.revision };
    }
    if (action === 'file.analysisAction') return { action: await resultFileAction(p, input.file) };
    if (action === 'access.save') {
      const result = await p.mutate(() => p.setAccess(input));
      for (const agent of ctx.agents.list()) if (liveProject(agent.session)?.id === p.id) updateTools(agent);
      return result;
    }
    if (action === 'project.checkpoint') {
      if (!input.paths?.length) throw new Error('Select the files to record');
      const source = input.sessionId ? await readSession(p, input.sessionId) : null;
      return p.mutate(() => checkpoint(p.root, input.message, input.paths, ownerFor(p, source)));
    }
    if (action === 'project.restorePreview') return prepareRestore(p, input);
    if (action === 'project.restore') return p.mutate(async () => restoreVersion(p, input, ownerFor(p, await readSession(base, input.sessionId))));
    if (action === 'project.diff') {
      if (input.revision && !/^[a-f0-9]{40,64}$/.test(input.revision)) throw new Error('Invalid revision');
      const files = input.revision
        ? await revisionFiles(p.root, input.revision)
        : await p.mutate(() => p.changedFiles());
      return { revision: input.revision || '', files };
    }
    if (action === 'project.fileDiff') {
      checkedPath(p.root, input.file);
      if (input.revision && !/^[a-f0-9]{40,64}$/.test(input.revision)) throw new Error('Invalid revision');
      const previous = input.revision ? input.revision + '^' : 'HEAD';
      const oldText = await git(p.root, ['show', previous + ':' + input.file], true).catch(() => '');
      const newText = input.revision ? await git(p.root, ['show', input.revision + ':' + input.file], true).catch(() => '') : await fs.readFile(checkedPath(p.root, input.file), 'utf8').catch(() => '');
      return { path: input.file, oldText, newText };
    }
    if (action === 'task.dismiss') {
      const job = (await p.jobs()).find(j => j.id === input.jobId);
      if (!job) throw new Error('Task not found');
      await p.saveJob({ ...job, acknowledged: true }); return { acknowledged: true };
    }
    if (action === 'task.refresh' || action === 'task.cancel') return jobUpdate(p, input.jobId, action === 'task.cancel' ? 'cancel' : 'status');
    if (action === 'task.collect-qe') return collectQE(p, resources, input.jobId, jobUpdate);
    if (action === 'conversation.messages' || action === 'conversation.document') {
      const session = await readSession(p, input.sessionId), messages = discussionMessages(session);
      if (action === 'conversation.messages') return { turns: discussionTurns(messages).map(turn => ({ index: turn.index, messages: turn.messages.map(m => ({ id: m.id, role: m.role, preview: m.text.replace(/\s+/g, ' ').slice(0, 120) })) })) };
      const message = messages.find(m => m.id === input.messageId && m.role === 'assistant');
      if (!message) throw new Error('Select an assistant answer');
      const title = message.text.split('\n').find(line => line.trim())?.replace(/^#+\s*/, '').slice(0, 80) || 'Research note';
      return { title, fileStem: englishStem(title), kind: 'source', content: message.text, sourceMessageIds: [message.id], sessionId: session.id, caseId: p.caseFor(session)?.id || null };
    }
    if (action === 'artifact.organize') {
      const parent = ctx.agents.get(input.currentSessionId || input.sessionId);
      if (!parent || workspaceFor(parent.session)?.id !== p.id) throw new Error('Open the discussion before organizing it');
      const source = await readSession(p, input.sessionId);
      const messages = selectDiscussion(discussionMessages(source), input);
      if (!messages.length) throw new Error('Choose discussion messages first');
      const prompt = editorPrompt + '\nRequested output language: ' + (input.language === 'en' ? 'English' : 'Chinese') + '\nSource session: ' + input.sessionId + '\n' + JSON.stringify(messages);
      const childId = randomUUID(); organizers.add(childId);
      const activation = await parent.ctx.get('subagents').startActivation({ childId, provider: 'spawn', label: input.language === 'en' ? 'Organize discussion' : '整理讨论成果', delivery: 'caller', signal: new AbortController().signal, request: { parent, prompt: [{ type: 'text', text: prompt }], maxDepth: 1 } });
      const job = { id: activation.childId, type: 'organize', label: input.language === 'en' ? 'Organize discussion' : '整理讨论成果', sessionId: source.id, caseId: p.caseFor(source)?.id || null, sourceMessageIds: messages.map(m => m.id), status: 'running', createdAt: Date.now() };
      drafts.set(job.id, activation); await p.saveJob(job);
      activation.result.then(async result => {
        const content = (result.output || []).filter(b => b.type === 'text').map(b => b.text).join('\n');
        const draft = !activation.userCancelled && result.stopReason === 'completed' ? parseArtifactDraft(content, messages) : {};
        await p.saveJob({ ...job, ...draft, status: activation.userCancelled ? 'killed' : draft.content ? 'completed' : 'failed', detail: draft.content || activation.userCancelled ? undefined : String(result.stopReason), finishedAt: Date.now() });
      }).catch(error => p.saveJob({ ...job, status: 'failed', detail: error.message })).finally(() => { drafts.delete(job.id); organizers.delete(job.id); });
      return job;
    }
    if (action === 'artifact.draft') {
      const job = (await p.jobs()).find(j => j.id === input.jobId && j.type === 'organize');
      if (!job) throw new Error('Draft task not found');
      return { ...job, status: job.status === 'running' && !drafts.has(job.id) ? 'interrupted' : job.status };
    }
    throw new Error('Unknown mat-agent operation');
  }
  ctx.effect(() => ctx.connection.fetch.register({ path: '/api/highzyme', methods: ['GET', 'POST'], requestBody: 'buffered', fetch: async request => {
    try { return Response.json(await api(request)); }
    catch (error) { return Response.json({ error: error.message }, { status: 400 }); }
  } }));
  for (const [name, file] of Object.entries({ echarts: 'echarts/dist/echarts.min.js', molecule: '3dmol/build/3Dmol-min.js' })) {
    ctx.effect(() => ctx.connection.fetch.register({ path: '/api/highzyme-assets/' + name, methods: ['GET'], requestBody: 'buffered', fetch: async () =>
      new Response(await fs.readFile(requireRuntime.resolve(file)), { headers: { 'Content-Type': 'text/javascript; charset=utf-8', 'Cache-Control': 'private, max-age=86400' } }) }));
  }
  const css = await fs.readFile(path.join(here, 'style.css'), 'utf8');
  const icon = await fs.readFile(path.join(here, 'material-mark.svg'), 'utf8');
  const iconUrl = 'data:image/svg+xml,' + encodeURIComponent(icon);
  ctx.on('webserver/index-inject', table => table.push({ kind: 'style', text: ':root{--hz-material-icon:url("' + iconUrl + '")}\n' + css }));
  ctx.inject(['webServer'], web => web.effect(() => web.webServer.tapIndex(html => html
    .replace(/<title>[^<]*<\/title>/, '<title>mat-agent</title>')
    .replace(/<link\b(?=[^>]*\brel=["'][^"']*icon[^"']*["'])[^>]*>/gi, '')
    .replace('</head>', '<link rel="icon" type="image/svg+xml" href="' + iconUrl + '"></head>'))));
}
