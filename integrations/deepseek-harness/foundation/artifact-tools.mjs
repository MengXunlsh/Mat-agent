import { candidateParameters, candidateValidation } from './case-research.mjs';
import { checkedPath } from './research.mjs';
import { science } from './science.mjs';
export function registerArtifactTools({ tool, requireProject, ownerFor, caseFor }) {
  tool('highzyme_artifact_save', 'Publish a project artifact and all its supporting data, code and graphics as one Git-versioned bundle. Built-in science tools already publish their outputs; do not register them twice. Use artifact_id for a revision. Keep hypotheses and verified results distinct.', {
    ...candidateParameters, title: { type: 'string', required: true }, kind: { type: 'string', enum: ['source', 'plan', 'result', 'code', 'data'], required: true },
    file_stem: { type: 'string', description: 'Lowercase English keywords joined with hyphens; application chooses the artifact folder' },
    file: { type: 'string', description: 'Project-relative existing file, or destination for supplied content' }, content: { type: 'string', description: 'Document content; omit to register an existing file' },
    artifact_id: { type: 'string' }, related_files: { type: 'array', items: { type: 'string' }, description: 'All project-relative supporting output files belonging to this result' },
    files: { type: 'object', additionalProperties: true, description: 'Output roles mapped to project-relative paths, e.g. report, result, data, code, png, svg; every value must be a path string' },
    source_references: { type: 'array', items: { type: 'string' } },
  }, async (args, exec) => {
    const p = await requireProject(exec);
    const validation = await candidateValidation(p, args, ownerFor(p, exec.agent.session));
    return p.mutate(async () => {
      const previous = p.data.artifacts.find(a => a.id === args.artifact_id || a.file === args.file);
      return p.publish({ ...args, validation, artifactId: args.artifact_id, fileStem: args.file_stem, relatedFiles: args.related_files, sourceReferences: args.source_references,
        ...(previous ? { sessionId: previous.sessionId, caseId: previous.caseId } : ownerFor(p, exec.agent.session)), checkpointOwner: ownerFor(p, exec.agent.session), enforceGrant: true });
    });
  });
  tool('highzyme_artifact_read', 'Read one file or list the files of a saved artifact bundle. A case reference pins the entire bundle to one Git commit. Text reads are bounded; materialize a binary/structured file for native read_image or scientific tools. Resolve localFile against the project directory for native readers.', {
    artifact_id: { type: 'string', required: true }, file: { type: 'string', description: 'Project-relative member path, output role such as report/result, or an unambiguous filename; omit for the main file' }, metadata_only: { type: 'boolean' }, materialize: { type: 'boolean' },
    offset: { type: 'integer' }, max_chars: { type: 'integer', description: '1 to 64000; default 16000' },
    view: { type: 'string', enum: ['text', 'dataset'], description: 'dataset reads all saved observations concisely from this pinned artifact version; text is the default' },
    fields: { type: 'array', items: { type: 'string' }, description: 'For dataset view, optional group.field or group names' },
    detail: { type: 'string', enum: ['values', 'full'], description: 'Dataset view: full includes original quotes/lineage; use with specific fields' },
  }, async (args, exec) => {
    const p = await requireProject(exec), c = caseFor(p, exec.agent.session);
    const caseId = c?.references.some(r => r.artifactId === args.artifact_id) ? c.id : undefined;
    if (args.view === 'dataset' && !args.metadata_only) {
      const saved = await p.readArtifact(args.artifact_id, caseId, true, { file: args.file, materialize: true, maxChars: 1 });
      const record = await science({ action: 'read_dataset_record', file: checkedPath(p.root, saved.localFile), fields: args.fields, detail: args.detail }, exec.signal);
      return { id: args.artifact_id, file: saved.file, revision: saved.revision, record };
    }
    return p.readArtifact(args.artifact_id, caseId, true,
      { file: args.file, metadataOnly: args.metadata_only, materialize: args.materialize, offset: args.offset, maxChars: args.max_chars ?? 16000 });
  });
}
