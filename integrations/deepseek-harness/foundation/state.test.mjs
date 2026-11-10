import test from 'node:test';
import assert from 'node:assert/strict';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { ComputeResources } from './state.mjs';

test('resource requires authentication and a live capability check; disabling and restart revoke submission', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hz-resource-'));
  const keys = new Map(); const credentials = { set: async (k,v) => keys.set(k,v), resolve: async k => keys.has(k) ? {value:keys.get(k)} : null, unset: async k => keys.delete(k) };
  let calls = 0;
  const server = http.createServer((req,res) => {
    assert.equal(req.headers.authorization, 'Bearer test-only'); res.setHeader('Content-Type','application/json');
    if (req.url === '/health') res.end(JSON.stringify({protocol:'highzyme-compute-v1',capabilities:['python']}));
    else { calls++; res.end(JSON.stringify({id:'job_test',status:'queued'})); }
  });
  await new Promise(r => server.listen(0,'127.0.0.1',r));
  try {
    const resources = new ComputeResources(root,credentials); await resources.load();
    const row = await resources.configure({url:`http://127.0.0.1:${server.address().port}`,token:'test-only'});
    await assert.rejects(resources.submit(row.id,{capability:'python'}), /DISABLED/);
    await resources.enable(row.id,true);
    await assert.rejects(resources.submit(row.id,{capability:'quantum_espresso'}), /does not provide/);
    await resources.submit(row.id,{capability:'python'}); assert.equal(calls,1);
    await resources.enable(row.id,false); await assert.rejects(resources.submit(row.id,{capability:'python'}));
    await resources.enable(row.id,true); await resources.load(); assert.equal(resources.get(row.id).enabled,false);
    assert.equal((await fs.readFile(path.join(root,'compute.json'),'utf8')).includes('test-only'),false);
    await resources.remove(row.id); assert.equal(keys.size,0);
  } finally { await new Promise(r=>server.close(r)); await fs.rm(root,{recursive:true,force:true}); }
});
