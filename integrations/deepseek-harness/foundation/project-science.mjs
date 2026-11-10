import path from 'node:path';
import { candidateParameters, candidateValidation } from './case-research.mjs';
import { existsSync } from 'node:fs';
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { checkedPath } from './research.mjs';
import { science } from './science.mjs';

export const analysisOptions = {
  ...candidateParameters,
  artifact_id: { type: 'string', description: 'Revise this existing artifact in place, keeping its ID and file paths' },
  new_analysis: { type: 'boolean', description: 'Create an independent result even when using the same inputs; do not combine with artifact_id' },
  output_prefix: { type: 'string', description: 'Optional project-relative prefix; a bare name uses the current case artifact folder. An existing prefix selects that analysis for revision' },
};
const presentation = new Set(['artifact_id', 'new_analysis', 'output_prefix', 'language', 'plot_layout', 'labels', 'x_label', 'y_label', 'dpi']);
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;

export async function resultFileAction(project, file) {
  if (!project.permitted(file)) return null;
  const target = checkedPath(project.root, file);
  if (!file.endsWith('-result.json') || (await fs.stat(target)).size > 32 * 1024 ** 2) return null;
  const data = JSON.parse(await fs.readFile(target, 'utf8'));
  return data.model === 'v = Vmax * S / (Km + S)' || data.groups?.[0]?.model === 'v = Vmax * S / (Km + S)' ? 'replotRates'
    : data.schema === 'highzyme.calculation.v1' && data.plot?.series?.length ? 'replotRates' : null;
}

async function selectAnalysis(project, args, owner, spec) {
  if (args.artifact_id && args.new_analysis) throw new Error('Choose revision or independent analysis');
  const operation = spec.action + ':' + spec.stem;
  const identity = Object.fromEntries(Object.entries(args).filter(([key, value]) => !presentation.has(key) && (!Array.isArray(value) || value.length)));
  const key = createHash('sha256').update(JSON.stringify(canonical({ operation, inputs: identity }))).digest('hex');
  let previous = args.artifact_id ? project.data.artifacts.find(a => a.id === args.artifact_id) : null;
  if (args.artifact_id && !previous) throw new Error('Artifact not found');
  if (!previous && !args.new_analysis) previous = project.data.artifacts.find(a => args.output_prefix
    ? a.analysis?.outputPrefix === args.output_prefix || a.file === args.output_prefix + '-report.md'
    : spec.replot ? a.relatedFiles?.includes(args.file)
    : a.sessionId === owner.sessionId && a.caseId === owner.caseId && a.analysis?.key === key);
  if (previous?.analysis && !spec.replot && previous.analysis.operation !== operation) throw new Error('Select an artifact for this analysis type');
  if (previous && spec.replot && !previous.relatedFiles.includes(args.file)) throw new Error('Replot the saved result belonging to this artifact');
  const previousPrefix = previous?.analysis?.outputPrefix || (previous?.file.endsWith('-report.md') ? previous.file.slice(0, -10) : null);
  if (previous && args.output_prefix && previousPrefix && args.output_prefix !== previousPrefix) throw new Error('A revision keeps the existing output prefix');
  let prefix = args.output_prefix || previousPrefix;
  if (!prefix) {
    const report = await project.artifactPath({ title: spec.title, fileStem: spec.stem + '-report', ...owner });
    const base = path.posix.dirname(report) + '/' + spec.stem;
    prefix = base;
    for (let n = 2; spec.suffixes.some(suffix => existsSync(checkedPath(project.root, prefix + suffix))); n++) prefix = base + '-' + n;
  }
  if (args.new_analysis && spec.suffixes.some(suffix => existsSync(checkedPath(project.root, prefix + suffix)))) throw new Error('Choose an unused prefix for an independent analysis');
  return { previous, prefix, analysis: spec.replot && previous ? previous.analysis : { key, operation, outputPrefix: prefix, inputs: spec.sources || [] } };
}

export async function projectScience(project, args, owner, spec, signal) {
  if (args.output_prefix && !/[\\/]/.test(args.output_prefix) && owner.caseId &&
      !project.data.artifacts.some(a => a.analysis?.outputPrefix === args.output_prefix)) {
    args = { ...args, output_prefix: project.case(owner.caseId).folder + '/artifacts/' + args.output_prefix };
  }
  const validation = args.candidate_id ? await candidateValidation(project, args, owner) : undefined;
  if (validation) args = { ...args, candidate_revision: validation.candidate_revision };
  const sources = spec.sources || [];
  for (const file of sources) {
    checkedPath(project.root, file);
    if (!project.permitted(file)) throw new Error('Grant read access to: ' + file);
  }
  const { previous, prefix, analysis } = await project.mutate(() => selectAnalysis(project, args, owner, spec));
  const outputs = spec.suffixes.map(s => prefix + s);
  for (const file of [...outputs, ...(previous?.relatedFiles || [])]) {
    checkedPath(project.root, file);
    if (!project.permitted(file, 'write')) throw new Error('Grant write access to: ' + file);
    if (outputs.includes(file) && sources.includes(file)) throw new Error('Do not overwrite an input source');
  }
  const result = await science({ ...args, ...spec.input, action: spec.action, output_prefix: checkedPath(project.root, prefix) }, signal);
  const files = Object.fromEntries(Object.entries(result.files).map(([key, value]) => [key, path.relative(project.root, value).split(path.sep).join('/')]));
  if (Object.values(files).some(file => !outputs.includes(file))) throw new Error('Scientific output does not match the planned project files');
  if (analysis && !spec.replot) analysis.replot = result.fit ? 'kinetics' : result.plot?.series?.length ? 'analysis' : null;
  const artifact = await project.mutate(async () => {
    const members = spec.replot && previous ? [...new Set([...previous.relatedFiles, ...Object.values(files)])] : Object.values(files);
    for (const file of members) if (!project.permitted(file, 'write')) throw new Error('Output access changed: ' + file);
    return project.publish({ artifactId: previous?.id, title: previous?.title || (spec.kind === 'source' && result.metadata?.title) || spec.title,
      file: previous?.file || files.report || files.svg || files.manifest, kind: previous?.kind || spec.kind || 'result',
      sessionId: previous?.sessionId || owner.sessionId, caseId: previous ? previous.caseId : owner.caseId, checkpointOwner: owner, enforceGrant: true,
      validation, relatedFiles: members, files: spec.replot && previous ? { ...previous.files, ...files } : files, analysis,
      sourceReferences: spec.replot && previous ? previous.sourceReferences : [...sources,
        ...(result.sources || []).map(source => source.file + ' SHA-256: ' + source.sha256),
        ...(result.fit?.source?.sha256 ? [sources[0] + ' SHA-256: ' + result.fit.source.sha256] : [])] });
  });
  return { ...result, files, artifact };
}
