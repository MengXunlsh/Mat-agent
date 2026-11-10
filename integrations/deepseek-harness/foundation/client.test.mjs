import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import vm from 'node:vm';

test('the browser API coalesces concurrent reads without caching mutations or failed responses', async () => {
  const source = await fs.readFile(new URL('./client.js', import.meta.url), 'utf8');
  const code = source.slice(source.indexOf('    const readActions = '), source.indexOf("    Object.assign(zh, { calculationStages:"));
  const calls = [];
  let fail = true;
  const server = http.createServer(async (request, response) => {
    let body = ''; for await (const chunk of request) body += chunk;
    const input = JSON.parse(body); calls.push(input);
    if (input.action === 'dataset.read' && fail) { fail = false; response.statusCode = 400; response.end(JSON.stringify({ error: 'Select a record' })); }
    else response.end(JSON.stringify({ value: input.value || 1 }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const api = vm.runInNewContext(code + '\napi;', { fetch: (url, options) => fetch(`http://127.0.0.1:${server.address().port}/${url}`, options) });
    const reads = await Promise.all([api('project.tasks', { projectId: 'p' }), api('project.tasks', { projectId: 'p' })]);
    assert.equal(reads[0].value, 1); assert.equal(calls.length, 1);
    await api('project.tasks', { projectId: 'p' }); assert.equal(calls.length, 2);
    await Promise.all([api('access.save', { value: 2 }), api('access.save', { value: 2 })]); assert.equal(calls.length, 4);
    await assert.rejects(api('dataset.read'), /Select a record/);
    assert.equal((await api('dataset.read')).value, 1);
    assert.equal(calls.length, 6);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});
