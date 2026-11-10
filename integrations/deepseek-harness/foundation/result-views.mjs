import { promises as fs } from 'node:fs';
import path from 'node:path';
import { science } from './science.mjs';

const structureName = file => /\.(cif|mmcif|pdb|mol|sdf|xyz|extxyz|vasp|poscar|contcar)$/i.test(file) || /(?:^|\/)(POSCAR|CONTCAR)$/.test(file);
const previews = new Map();

export async function artifactVisual(project, input) {
  const metadata = await project.readArtifact(input.artifactId, input.caseId, false, { metadataOnly: true });
  const key = project.root + '\0' + input.artifactId + '\0' + metadata.revision;
  if (!previews.has(key)) {
    const pending = buildArtifactVisual(project, { ...metadata, id: input.artifactId }).catch(error => { previews.delete(key); throw error; });
    previews.set(key, pending);
    if (previews.size > 16) previews.delete(previews.keys().next().value);
  }
  const pending = previews.get(key); previews.delete(key); previews.set(key, pending);
  return { ...await pending, artifact: metadata };
}

async function buildArtifactVisual(project, metadata) {
  const roles = { ...metadata.files };
  roles.options ||= roles.plot_options;
  if (/\.csv$/i.test(roles.data || '')) { roles.table ||= roles.data; delete roles.data; }
  if (!roles.result && !roles.data) {
    const result = metadata.relatedFiles.find(f => /(?:result|evidence|comparison)\.json$/i.test(f));
    if (result) roles.result = result;
  }
  if (!roles.structure) {
    const file = metadata.relatedFiles.find(structureName);
    if (file) roles.structure = file;
  }
  const selected = Object.entries(roles).filter(([role, file]) => file && (role.startsWith('structure_') || ['result', 'data', 'table', 'structure', 'final_structure', 'qe_out', 'options', 'request'].includes(role)));
  const saved = await project.materializeArtifactFiles(metadata, selected.map(([, file]) => file));
  const files = Object.fromEntries(selected.map(([role, file]) => [role, saved[file]]));
  const request = files.request ? JSON.parse(await fs.readFile(files.request, 'utf8')) : {};
  const view = await science({ action: 'result_view', files, input: request });
  if (view.kind === 'kinetics' && view.saved_layout === 'panels') view.figure_file = roles.svg || roles.png;
  view.images = metadata.relatedFiles.filter(file => /\.(png|jpe?g|webp|svg)$/i.test(file))
    .filter(file => (!view.charts.length || /-roi-\d+\./.test(file)) && !(view.depiction && /-structure\.svg$/i.test(file))).map(file => ({ file, label: path.basename(file) }));
  return view;
}

export async function artifactMedia(project, input) {
  if (!/\.(png|jpe?g|webp|svg)$/i.test(input.file)) throw new Error('Select an artifact image');
  const saved = await project.readArtifact(input.artifactId, input.caseId, false, { file: input.file, materialize: true, maxChars: 1 });
  const bytes = await fs.readFile(path.join(project.root, saved.localFile));
  const ext = path.extname(input.file).slice(1).toLowerCase();
  const type = { svg: 'image/svg+xml', jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp' }[ext];
  return { url: 'data:' + type + ';base64,' + bytes.toString('base64'), revision: saved.revision };
}
