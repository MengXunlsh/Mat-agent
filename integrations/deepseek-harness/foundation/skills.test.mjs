import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const requireRuntime = createRequire(new URL('../web-runtime/package.json', import.meta.url));
const { FileSystemSkillProvider } = await import(pathToFileURL(requireRuntime.resolve('@deepseek-ai/dsh-skill-filesystem')));

const { Context } = await import(pathToFileURL(requireRuntime.resolve('@deepseek-ai/cordis')));

test('native Harness discovers and loads the bundled research capabilities', async () => {
  const abort = new AbortController();
  const provider = new FileSystemSkillProvider(new Context(), { signal: abort.signal, invalidate() {} }, {
    includeDefaultRoots: false, watch: false, bundledSkillDir: fileURLToPath(new URL('./skills', import.meta.url)),
  });
  try {
    const options = { cwd: process.cwd(), signal: abort.signal };
    const candidates = await provider.list(options);
    assert.deepEqual(candidates.map(c => c.name).sort(), ['application-exploration', 'assay-comparison', 'compute-resource-setup', 'discussion-artifact', 'formulation-calculations', 'image-colorimetry', 'initial-rate-kinetics', 'literature-evidence', 'material-design', 'material-structure-check', 'nanozyme-dataset', 'publication-retrieval', 'reaction-simulation', 'scientific-computing', 'scientific-plotting', 'signal-analysis']);
    const comparison = await provider.get(candidates.find(c => c.name === 'assay-comparison'), options);
    assert.match(comparison.content, /highzyme_compare_evidence/);
    assert.equal(comparison.source, 'bundled');
    const computing = await provider.get(candidates.find(c => c.name === 'scientific-computing'), options);
    assert.match(computing.content, /highzyme_qe_workflow_prepare/);
  } finally { await provider.dispose(); }
});
