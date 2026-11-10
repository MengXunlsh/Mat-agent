import path from 'node:path';
import { createHash } from 'node:crypto';
import { checkedPath } from './research.mjs';
import { projectScience, analysisOptions } from './project-science.mjs';

export function registerDocumentTools({ tool, requireProject, ownerFor }) {
  tool('highzyme_render_document', 'Render 1 to 4 selected project PDF pages to PNG with a source hash and page locators. Then use native read_image with the selected vision-capable model. No separate model API is called by the renderer.', {
    file: { type: 'string', required: true }, pages: { type: 'array', required: true, items: { type: 'integer' } },
    dpi: { type: 'integer' }, ...analysisOptions, language: { type: 'string', enum: ['zh', 'en'] },
  }, async (args, exec) => {
    const p = await requireProject(exec);
    if (!args.pages.length || args.pages.length > 4) throw new Error('Select 1 to 4 PDF pages');
    const name = path.basename(args.file).replace(/\.[^.]+$/, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'document';
    const stem = name + '-' + createHash('sha256').update(args.file).digest('hex').slice(0, 8);
    return projectScience(p, args, ownerFor(p, exec.agent.session), { action: 'render_document', stem: stem + '-pages',
      title: args.language === 'zh' ? '文献页面' : 'Document pages', sources: [args.file],
      suffixes: ['-report.md', '-manifest.json', ...args.pages.map(page => '-page-' + page + '.png')],
      input: { file: checkedPath(p.root, args.file), source_label: args.file } }, exec.signal);
  });
  tool('highzyme_retrieve_publication', 'Retrieve an explicitly identified public paper or ACS supporting information into the project. Accept DOI links, bare DOI, PMC:PMCID or MED:PMID. document_id=article gets available text; supplements lists ACS SI; choose a returned SI identifier to download its PDF. No general database search.', {
    source: { type: 'string', required: true }, document_id: { type: 'string' },
    ...analysisOptions, language: { type: 'string', enum: ['zh', 'en'] },
  }, async (args, exec) => {
    const p = await requireProject(exec);
    if (!p.access.network) throw new Error('Enable network access before retrieving publications');
    const identity = args.source + '/' + (args.document_id || 'article');
    const stem = 'publication-' + args.source.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 56).replace(/-$/, '') + '-' + createHash('sha256').update(identity).digest('hex').slice(0, 8);
    return projectScience(p, args, ownerFor(p, exec.agent.session), { action: 'retrieve_publication', stem,
      title: args.language === 'zh' ? '指定文献与补充材料' : 'Publication and supporting information', kind: 'source',
      suffixes: ['-report.md', '-manifest.json', '-source.md', '-source.pdf', '-source.xml'], input: {} }, exec.signal);
  });
}
