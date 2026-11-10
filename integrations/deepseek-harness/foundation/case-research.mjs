import fs from 'node:fs/promises';
import { randomUUID, createHash } from 'node:crypto';
import { checkedPath } from './research.mjs';
import { science } from './science.mjs';

export const RESEARCH_WORKFLOWS = {
  general: { skill: null, steps: ['objective', 'evidence', 'analysis', 'report'] },
  'application-exploration': { skill: 'application-exploration', steps: ['objective', 'evidence', 'applications', 'review', 'validation'] },
  'material-design': { skill: 'material-design', steps: ['objective', 'evidence', 'designs', 'review', 'validation'] },
};

export const candidateParameters = {
  candidate_id: { type: 'string', description: 'Optional candidate in the active case being tested' },
  validation_question: { type: 'string', description: 'Question this operation answers' },
  validation_criterion: { type: 'string', description: 'Criterion used to interpret the result; defaults to the candidate plan' },
  validation_comparison: { type: 'string', description: 'Comparison for this operation when it differs from the candidate plan' },
};

function proposalRevision(candidate) {
  const fields = ['kind', 'hypothesis', 'baseline', 'application', 'design', 'composition', 'validation', 'uncertainties', 'evidence', 'based_on', 'research_context'];
  return createHash('sha256').update(JSON.stringify(fields.map(key => candidate[key] ?? null))).digest('hex').slice(0, 16);
}

function candidateState(candidate) {
  candidate.proposal_revision ||= proposalRevision(candidate);
  const current = candidate.feedback.filter(f => f.candidate_revision === candidate.proposal_revision);
  candidate.validation_outcome = current.at(-1)?.outcome || 'not_validated';
  candidate.status = candidate.screening?.rejected ? 'rejected' : candidate.validation_outcome === 'contradicts' ? 'needs_revision'
    : !candidate.evidence.length ? 'needs_evidence' : ['method', 'comparison', 'criterion'].every(k => candidate.validation?.[k]?.trim()) ? 'ready_for_validation' : 'needs_information';
  return candidate;
}

export async function candidateValidation(project, input, owner) {
  if (!input.candidate_id) return undefined;
  const c = owner.caseId && project.case(owner.caseId);
  if (!c || c.status !== 'active') throw new Error('Open the candidate research case first');
  const state = await caseResearch(project, c), row = state.candidates.find(v => v.id === input.candidate_id);
  if (!row || row.status === 'rejected') throw new Error('Choose a retained candidate from the active case');
  const question = input.validation_question || row.validation?.method, criterion = input.validation_criterion || row.validation?.criterion;
  if (!question?.trim() || !criterion?.trim()) throw new Error('Specify the validation question and criterion');
  const artifact = project.data.artifacts.find(a => a.file === c.research.file);
  const source = await project.readArtifact(artifact.id, undefined, true, { metadataOnly: true });
  return { case_id: c.id, candidate_id: row.id, candidate_revision: row.proposal_revision, candidate_title: row.title,
    hypothesis: row.hypothesis, question, comparison: input.validation_comparison || (input.validation_question ? null : row.validation?.comparison || row.baseline), criterion,
    source: { artifact_id: artifact.id, file: source.file, revision: source.revision, sha256: source.sha256 } };
}

export async function researchValidations(project, c) {
  if (!c?.research?.file || !project.permitted(c.research.file)) return { tasks: [], results: [] };
  return { tasks: (await project.jobs()).filter(j => j.validation?.case_id === c.id),
    results: project.data.artifacts.filter(a => a.validation?.case_id === c.id && project.permitted(a.file)) };
}

export async function caseResearch(project, c) {
  if (!c?.research?.file) return { kind: c?.research?.kind || 'general', objective: c?.research?.kind ? c.title : '', constraints: [], stage: 'objective', candidates: [] };
  if (!project.permitted(c.research.file)) throw new Error('Grant read access to the case research file');
  const state = JSON.parse(await fs.readFile(checkedPath(project.root, c.research.file), 'utf8'));
  state.candidates.forEach(candidateState); return state;
}

async function sourceReferences(project, c, ids) {
  const refs = [];
  for (const id of [...new Set(ids || [])]) {
    const a = project.data.artifacts.find(a => a.id === id);
    if (!a || a.file === c.research?.file) throw new Error('Choose an existing source artifact');
    const pinned = c.references.find(ref => ref.artifactId === id);
    const metadata = await project.readArtifact(id, pinned ? c.id : undefined, true, { metadataOnly: true });
    refs.push({ artifact_id: id, file: metadata.file, revision: metadata.revision, sha256: metadata.sha256 });
  }
  for (const ref of refs) if (!c.references.some(r => r.artifactId === ref.artifact_id)) await project.reference(c.id, ref.artifact_id);
  return refs;
}

function report(state) {
  const zh = state.language !== 'en';
  const labels = zh ? { general: '通用研究', 'application-exploration': '应用方向探索', 'material-design': '材料候选设计', objective: '明确目标', evidence: '证据整理', applications: '应用方向', designs: '材料设计', review: '核查与筛选', validation: '验证与反馈', analysis: '研究分析', report: '成果整理', needs_evidence: '待补证据', needs_information: '待补信息', ready_for_validation: '可安排验证', rejected: '已排除', reviewed: '已有反馈', not_validated: '未验证', needs_revision: '待修订', formula: '组成式', stoichiometry: '计量关系', charge_balance: '电荷平衡', pass: '通过', fail: '不通过', unknown: '未知', supports: '支持', contradicts: '矛盾', inconclusive: '尚不能判断' } : {};
  const label = key => labels[key] || key.replaceAll('_', ' ').replaceAll('-', ' ');
  const lines = ['# ' + (zh ? '案例研究计划' : 'Case research plan'), '', state.objective, '',
    (zh ? '研究类型：' : 'Workflow: ') + label(state.kind), (zh ? '当前阶段：' : 'Current stage: ') + label(state.stage), '',
    '## ' + (zh ? '要求' : 'Requirements'), ...state.constraints.map(s => '- ' + s), ''];
  for (const c of state.candidates) {
    lines.push('## ' + c.title, '', c.hypothesis, '', c.design || c.application || '', '',
      (zh ? '对照：' : 'Baseline: ') + c.baseline, (zh ? '方案状态：' : 'Proposal: ') + label(c.status),
      (zh ? '验证结论：' : 'Validation outcome: ') + label(c.validation_outcome),
      (zh ? '方案版本：' : 'Proposal version: ') + c.proposal_revision,
      ...(c.based_on ? [(zh ? '承接应用：' : 'Based on application: ') + c.based_on.title + ' @ ' + c.based_on.candidate_revision] : []),
      ...(c.screening?.checks || []).map(v => '- ' + label(v.name) + ': ' + label(v.status) + (zh ? '' : ' — ' + v.detail)),
      ...c.uncertainties.map(s => '- ' + s), '', '### ' + (zh ? '验证' : 'Validation'),
      c.validation?.method || '', c.validation?.comparison || '', c.validation?.criterion || '', '',
      ...c.evidence.map(r => '- ' + r.file + ' @ ' + r.revision), '',
      ...c.feedback.map(f => '- ' + label(f.outcome) + ': ' + f.summary + ' (' + f.source.file + ' @ ' + f.source.revision + '; ' + (zh ? '方案版本 ' : 'proposal ') + (f.candidate_revision || (zh ? '未记录' : 'unrecorded')) + ')'), '');
  }
  return lines.join('\n') + '\n';
}

export async function updateCaseResearch(project, c, input, owner) {
  if (!c || c.status !== 'active') throw new Error('Open an active research case first');
  return project.mutate(async () => {
    const state = await caseResearch(project, c);
    const original = JSON.stringify(state);
    const action = input.action || 'configure';
    if (action === 'configure') {
      const kind = input.kind || state.kind;
      if (!RESEARCH_WORKFLOWS[kind]) throw new Error('Unknown case research workflow');
      if (kind !== state.kind) state.stage = 'objective';
      state.kind = kind;
      if (input.objective !== undefined) state.objective = input.objective.trim();
      if (input.constraints !== undefined) {
        if (!Array.isArray(input.constraints) || input.constraints.some(v => typeof v !== 'string')) throw new Error('Requirements must be text items');
        state.constraints = input.constraints.filter(v => v.trim());
      }
    } else if (action === 'candidate') {
      const supplied = input.candidate;
      if (supplied && ['title', 'hypothesis', 'baseline', 'application', 'design'].some(key => supplied[key] !== undefined && typeof supplied[key] !== 'string') ||
          supplied?.validation && ['method', 'comparison', 'criterion'].some(key => supplied.validation[key] !== undefined && typeof supplied.validation[key] !== 'string')) throw new Error('Candidate title, hypothesis, baseline, application, design and validation method/comparison/criterion must be text strings');
      if (!supplied?.title?.trim() || !supplied.hypothesis?.trim() || !supplied.baseline?.trim()) throw new Error('candidate.title, candidate.hypothesis and candidate.baseline are required nonempty text fields; baseline describes the comparison');
      const kind = supplied.kind || state.kind;
      if (!['application-exploration', 'material-design'].includes(kind) || !(kind === 'material-design' ? supplied.design : supplied.application)?.trim()) throw new Error('Specify the candidate application or material design');
      const previous = supplied.id && state.candidates.find(v => v.id === supplied.id);
      if (supplied.id && !previous) throw new Error('Candidate not found');
      if (supplied.uncertainties && (!Array.isArray(supplied.uncertainties) || supplied.uncertainties.some(v => typeof v !== 'string'))) throw new Error('Uncertainties must be text items');
      const parentId = supplied.parent_candidate_id || previous?.based_on?.candidate_id;
      const parent = parentId && state.candidates.find(v => v.id === parentId && v.kind === 'application-exploration');
      if (parentId && (!parent || kind !== 'material-design')) throw new Error('candidate.parent_candidate_id must identify an application-exploration candidate in this case; describe material comparisons in candidate.baseline instead');
      const basedOn = parent && { candidate_id: parent.id, candidate_revision: parent.proposal_revision, title: parent.title, application: parent.application };
      const screening = kind === 'material-design' ? await science({ ...(supplied.composition || {}), action: 'candidate_check' }) : null;
      const evidence = await sourceReferences(project, c, supplied.evidence_artifact_ids || []);
      const row = { id: previous?.id || randomUUID(), kind, title: supplied.title.trim(), hypothesis: supplied.hypothesis.trim(),
        baseline: supplied.baseline.trim(), application: supplied.application || '', design: supplied.design || '',
        ...(basedOn ? { based_on: basedOn } : {}), research_context: { objective: state.objective, constraints: state.constraints },
        composition: supplied.composition || null, validation: supplied.validation || {}, uncertainties: supplied.uncertainties || [],
        evidence, screening,
        feedback: previous?.feedback || [] };
      row.proposal_revision = proposalRevision(row); candidateState(row);
      if (previous) Object.assign(previous, row); else state.candidates.push(row);
    } else if (action === 'feedback') {
      const candidate = state.candidates.find(v => v.id === input.candidate_id);
      if (!candidate || !input.summary?.trim() || !['supports', 'contradicts', 'inconclusive'].includes(input.outcome)) throw new Error('Choose a candidate, outcome and result summary');
      const result = project.data.artifacts.find(a => a.id === input.source_artifact_id);
      if (!result || !['source', 'data', 'result'].includes(result.kind)) throw new Error('Feedback needs a saved source, data or result artifact');
      const kind = input.validation_kind || 'analysis';
      if (!['literature', 'analysis', 'calculation', 'experiment'].includes(kind)) throw new Error('Choose the validation result type');
      const job = input.job_id && (await project.jobs()).find(j => j.id === input.job_id);
      if (input.job_id && (!job?.validation || job.artifactId !== result.id)) throw new Error('Choose the result artifact of the linked validation task');
      const pinned = c.references.some(r => r.artifactId === result.id) ? await project.readArtifact(result.id, c.id, true, { metadataOnly: true }) : result;
      const binding = job?.validation || pinned.validation;
      if (job && pinned.validation && pinned.validation.candidate_revision !== job.validation.candidate_revision) throw new Error('The pinned result belongs to another proposal version');
      if (binding && (binding.case_id !== c.id || binding.candidate_id !== candidate.id)) throw new Error('This result belongs to a different candidate');
      const revision = input.candidate_revision || binding?.candidate_revision || candidate.proposal_revision;
      if (!/^[a-f0-9]{16}$/.test(revision) || binding && binding.candidate_revision !== revision) throw new Error('Feedback must use the tested candidate version');
      const [source] = await sourceReferences(project, c, [input.source_artifact_id]);
      candidate.feedback.push({ candidate_revision: revision, ...(job ? { job_id: job.id } : {}), outcome: input.outcome, kind, summary: input.summary.trim(), source, time: Date.now() });
      candidateState(candidate);
    } else if (action !== 'stage') throw new Error('Unknown case research action');
    if (input.stage !== undefined) {
      if (!RESEARCH_WORKFLOWS[state.kind].steps.includes(input.stage)) throw new Error('Unknown research stage');
      state.stage = input.stage;
    }
    const language = input.language || state.language || 'zh';
    if (state.schema && JSON.stringify(state) === original && state.language === language) return { ...state, artifact: project.data.artifacts.find(a => a.file === c.research.file) };
    state.schema = 'highzyme.case.research.v1'; state.language = language; state.updatedAt = Date.now();
    const file = c.research?.file || c.folder + '/research-plan.json';
    const markdown = file.replace(/\.json$/, '.md');
    if (!project.permitted(markdown, 'write') || !project.permitted(markdown) || !project.permitted(file, 'write')) throw new Error('Grant access to the case research files');
    c.research = { kind: state.kind, stage: state.stage, file };
    await fs.writeFile(checkedPath(project.root, markdown), report(state));
    const saved = await project.publish({ title: state.language === 'en' ? 'Case research plan' : '案例研究计划',
      file, kind: 'plan', content: JSON.stringify(state, null, 2) + '\n', ...owner, caseId: c.id, enforceGrant: true,
      files: { data: file, report: markdown }, relatedFiles: [markdown],
      sourceReferences: [...new Set(state.candidates.flatMap(row => [...row.evidence.map(ref => ref.artifact_id), ...row.feedback.map(f => f.source.artifact_id)]))] });
    return { ...state, artifact: saved };
  });
}

export function registerCaseResearchTools({ tool, requireProject, ownerFor, caseFor }) {
  tool('highzyme_candidate_check', 'Check an explicit candidate composition and supplied oxidation states. Returns unknown for missing information. No structural stability, eg occupancy or performance is inferred from a formula.', {
    formula: { type: 'string' }, species: { type: 'array', items: { type: 'object', additionalProperties: false, properties: { element: { type: 'string', required: true }, count: { type: 'number', required: true }, oxidation_state: { type: 'number', required: true } } } }, target_charge: { type: 'number' },
  }, async (args, exec) => { await requireProject(exec); return science({ action: 'candidate_check', ...args }); });
  tool('highzyme_case_research', 'Read or update the active case research workflow. Configure an application-exploration or material-design task; record grounded candidates, move to a relevant stage, or link actual feedback. Uses native project artifacts and Git. It never submits computation or starts model calls.', {
    action: { type: 'string', required: true, enum: ['read', 'configure', 'candidate', 'feedback', 'stage'] },
    kind: { type: 'string', enum: Object.keys(RESEARCH_WORKFLOWS) }, objective: { type: 'string' }, constraints: { type: 'array', items: { type: 'string' } },
    stage: { type: 'string' }, candidate: { type: 'object', additionalProperties: true, properties: {
      id: { type: 'string' }, title: { type: 'string', description: 'Required for candidate: concise name' }, hypothesis: { type: 'string', description: 'Required for candidate: falsifiable claim, not an established performance result' }, baseline: { type: 'string', description: 'Required for candidate: comparison material or condition, as text; not parent_candidate_id' },
      kind: { type: 'string', enum: ['application-exploration', 'material-design'] }, application: { type: 'string' }, design: { type: 'string' },
      parent_candidate_id: { type: 'string', description: 'Only a material-design candidate may reference an application-exploration candidate in this case. Do not use a material baseline ID here.' },
      evidence_artifact_ids: { type: 'array', items: { type: 'string' } }, uncertainties: { type: 'array', items: { type: 'string' } },
      validation: { type: 'object', additionalProperties: true, properties: { method: { type: 'string' }, comparison: { type: 'string' }, criterion: { type: 'string' } } },
    }, description: 'Text title/hypothesis/baseline and application or design. validation method/comparison/criterion must be strings, not nested objects. Optional parent_candidate_id and composition:{formula,species,target_charge}; id revises a candidate.' },
    candidate_id: { type: 'string' }, candidate_revision: { type: 'string', description: 'Tested proposal version; defaults to the result binding or current proposal' }, job_id: { type: 'string' }, source_artifact_id: { type: 'string' }, outcome: { type: 'string', enum: ['supports', 'contradicts', 'inconclusive'] }, validation_kind: { type: 'string', enum: ['literature', 'analysis', 'calculation', 'experiment'] }, summary: { type: 'string' }, language: { type: 'string', enum: ['zh', 'en'] },
  }, async (args, exec) => {
    const p = await requireProject(exec), c = caseFor(p, exec.agent.session);
    if (args.action === 'read') return { workflows: RESEARCH_WORKFLOWS, case: c, research: await caseResearch(p, c), validations: await researchValidations(p, c) };
    return updateCaseResearch(p, c, args, ownerFor(p, exec.agent.session));
  });
}
