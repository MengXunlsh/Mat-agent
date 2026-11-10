import fs from 'node:fs/promises';
import { checkedPath } from './research.mjs';
import { projectScience } from './project-science.mjs';

export async function projectEvidence(project, args, owner, action, signal) {
  const read = file => {
    const resolved = checkedPath(project.root, file);
    if (!project.permitted(file)) throw new Error('Grant read access to: ' + file);
    return resolved;
  };
  let input;
  const sources = [];
  if (action === 'save_evidence') {
    const file = read(args.file);
    if ((await fs.stat(file)).size > 32 * 1024 ** 2) throw new Error('Evidence file exceeds 32 MiB');
    const data = JSON.parse(await fs.readFile(file, 'utf8'));
    if (!Array.isArray(data.facts)) throw new Error('Evidence needs a facts array');
    for (const fact of data.facts) for (const ref of fact.evidence || []) { read(ref.file); sources.push(ref.file); }
    input = { file };
    sources.push(args.file);
  } else {
    if (!Array.isArray(args.selections) || !args.selections.length) throw new Error('Select evidence files and assay IDs');
    input = { selections: args.selections.map(selection => {
      if (!Array.isArray(selection.assay_ids) || !selection.assay_ids.length) throw new Error('Select assay IDs');
      sources.push(selection.file);
      return { ...selection, file: read(selection.file), source_label: selection.file };
    }) };
  }
  const stem = action === 'save_evidence' ? 'literature-evidence' : 'assay-comparison';
  const suffixes = action === 'save_evidence' ? ['-evidence.json', '-evidence.csv', '-report.md'] : ['-comparison.json', '-comparison.csv', '-report.md'];
  const title = action === 'save_evidence' ? (args.language === 'zh' ? '文献证据' : 'Literature evidence') : (args.language === 'zh' ? '材料与测定条件比较' : 'Material and assay comparison');
  return projectScience(project, args, owner, { action, stem, title, sources: [...new Set(sources)], suffixes,
    input: { ...input, root: project.root } }, signal);
}
