import test from 'node:test';
import assert from 'node:assert/strict';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ResearchProject } from './research.mjs';
import { artifactVisual, artifactMedia } from './result-views.mjs';

test('visual previews and images use the same pinned artifact bundle across later edits', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-view-'));
  try {
    const p = await new ResearchProject({ id: 'view', path: root }).load();
    const c = await p.createCase('Pinned analysis');
    const file = path.join(root, 'result.json');
    const first = { schema: 'highzyme.calculation.v1', calculation: 'reaction', summary: { operation: 'network' },
      data: {}, plot: { x_label: 'Time (s)', y_label: 'Concentration (M)', series: [{ label: 'A', x: [0, 1], y: [1, .5] }] } };
    await fs.writeFile(file, JSON.stringify(first));
    await fs.writeFile(path.join(root, 'plot.svg'), '<svg xmlns="http://www.w3.org/2000/svg"><text>Original</text></svg>');
    let a = await p.publish({ title: 'Reaction', file: 'result.json', relatedFiles: ['result.json', 'plot.svg'], files: { result: 'result.json', svg: 'plot.svg' }, sessionId: 'discussion' });
    await p.reference(c.id, a.id);
    first.plot.series[0].y = [1, .1];
    await fs.writeFile(file, JSON.stringify(first)); await fs.writeFile(path.join(root, 'plot.svg'), '<svg>Changed</svg>');
    a = await p.publish({ artifactId: a.id, title: 'Reaction', file: 'result.json', relatedFiles: a.relatedFiles, files: a.files, sessionId: 'discussion' });
    assert.deepEqual((await artifactVisual(p, { artifactId: a.id, caseId: c.id })).charts[0].series[0].y, [1, .5]);
    assert.deepEqual((await artifactVisual(p, { artifactId: a.id })).charts[0].series[0].y, [1, .1]);
    const image = await artifactMedia(p, { artifactId: a.id, caseId: c.id, file: 'plot.svg' });
    assert.match(Buffer.from(image.url.split(',')[1], 'base64').toString(), /Original/);
    await assert.rejects(artifactMedia(p, { artifactId: a.id, file: 'private.svg' }), /Select a file/);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('batch materialization preserves binary bytes, Unicode paths and exact saved versions', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'highzyme-batch-'));
  try {
    const p = await new ResearchProject({ id: 'batch', path: root }).load();
    await fs.writeFile(path.join(root, '.gitattributes'), '* -text\n');
    const binary = Buffer.from([0, 10, 255, 32, 0, 13]), text = Buffer.from('原始数据\r\nsecond line\n');
    await fs.writeFile(path.join(root, 'raw.bin'), binary);
    await fs.writeFile(path.join(root, 'source 中文.txt'), text);
    const a = await p.publish({ title: 'Bundle', file: 'source 中文.txt', relatedFiles: ['source 中文.txt', 'raw.bin'] });
    const metadata = await p.readArtifact(a.id, undefined, false, { metadataOnly: true });
    await fs.writeFile(path.join(root, 'raw.bin'), Buffer.from('unsaved edits'));
    const files = await p.materializeArtifactFiles(metadata, ['source 中文.txt', 'raw.bin']);
    assert.deepEqual(await fs.readFile(files['raw.bin']), binary);
    assert.deepEqual(await fs.readFile(files['source 中文.txt']), text);
    await assert.rejects(p.materializeArtifactFiles(metadata, ['private.txt']), /artifact version/);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});
