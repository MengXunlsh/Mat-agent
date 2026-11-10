import fs from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { checkedPath, git } from './research.mjs';

export async function delegateResearch({ ctx, project, parent, args, owner, activations }) {
  if (parent.session.header.origin === 'subagent') throw new Error('Return this bounded assignment to the parent instead of starting another research role');
  const roles = { literature: ['literature.md', 'literature-extraction-draft.json'],
    analysis: ['analysis.md', 'data-analysis-report.md'], verification: ['verification.md', 'evidence-review.md'] };
  const [reference, filename] = roles[args.role];
  for (const file of args.files) {
    checkedPath(project.root, file);
    if (!project.permitted(file)) throw new Error('Grant read access to: ' + file);
  }
  const previous = args.artifact_id && project.data.artifacts.find(a => a.id === args.artifact_id);
  if (args.artifact_id && !previous) throw new Error('Artifact not found');
  if (previous && args.output_file && args.output_file !== previous.file && args.role !== 'literature') throw new Error('A report revision keeps its existing path');
  const output = args.output_file || (args.role !== 'literature' && previous?.file) || await project.mutate(() => project.artifactPath({ fileStem: filename.replace(/\.[^.]+$/, ''), title: filename, ...owner })).then(file => file.replace(/\.md$/, args.role === 'literature' ? '.json' : '.md'));
  checkedPath(project.root, output);
  if (!project.permitted(output, 'write')) throw new Error('Grant write access to the task output');
  if (args.files.includes(output)) throw new Error('Use a separate output file for this assignment');
  const instructions = await fs.readFile(new URL('./agents/' + reference, import.meta.url), 'utf8');
  const prompt = instructions + '\nAssignment: ' + args.goal + '\n' + JSON.stringify({ role: args.role, project_root: project.root,
    input_artifacts: [...new Set(args.files.map(file => project.data.artifacts.find(a => (a.relatedFiles || [a.file]).includes(file))).filter(Boolean))].map(a => ({ artifact_id: a.id, file: a.file, revision: project.data.cases.find(c => c.id === owner.caseId)?.references.find(r => r.artifactId === a.id)?.revision || a.revision })),
    input_files: args.files, output_file: output, artifact_id: args.artifact_id, output_language: args.language || 'zh' }) +
    '\nResolve project-relative paths against project_root. Use only the assigned sources and existing authorized project context. Write the deliverable to output_file, then return only the decision-relevant findings, source locators, unresolved issues and file paths. Do not repeat the full report in the final message. Do not spawn further agents.';
  const label = { literature: ['文献处理', 'Literature processing'], analysis: ['数据分析', 'Data analysis'], verification: ['证据核对', 'Evidence review'] }[args.role][args.language === 'en' ? 1 : 0];
  const activation = await parent.ctx.get('subagents').startActivation({ childId: randomUUID(), provider: 'spawn', label,
    delivery: 'caller', signal: new AbortController().signal,
    request: { parent, prompt: [{ type: 'text', text: prompt }], maxDepth: 1 } });
  const job = { id: activation.childId, type: 'research', role: args.role, label, ...owner, files: args.files,
    outputFile: output, status: 'running', createdAt: Date.now() };
  activations.set(job.id, activation); await project.saveJob(job);
  activation.result.then(async result => {
    const summary = (result.output || []).filter(block => block.type === 'text').map(block => block.text).join('\n').slice(0, 12000);
    const written = await fs.stat(checkedPath(project.root, output)).then(info => info.isFile(), () => false);
    const status = activation.userCancelled ? 'killed' : result.stopReason === 'completed' && written ? 'completed' : 'failed';
    let artifact;
    if (status === 'completed' && args.role !== 'literature' && project.permitted(output, 'write') && project.permitted(output)) {
      artifact = await project.mutate(async () => {
        const published = project.data.artifacts.find(a => a.file === output);
        if (published && !(await git(project.root, ['diff', 'HEAD', '--name-only', '--', ...(published.relatedFiles || [output])])).length) return published;
        return project.publish({ artifactId: published?.id, title: published?.title || label, file: output, kind: 'result',
          sessionId: published?.sessionId || owner.sessionId, caseId: published ? published.caseId : owner.caseId,
          checkpointOwner: owner, sourceReferences: [...new Set([...(published?.sourceReferences || []), ...args.files])], enforceGrant: true });
      });
    }
    await project.saveJob({ ...job, status, summary, artifactId: artifact?.id, detail: status === 'failed' ? !written ? 'The assigned output file was not written' : result.stopReason : undefined, finishedAt: Date.now() });
  }).catch(error => project.saveJob({ ...job, status: 'failed', detail: error.message, finishedAt: Date.now() })).finally(() => activations.delete(job.id));
  return { ...job, agent_id: activation.childId };
}
