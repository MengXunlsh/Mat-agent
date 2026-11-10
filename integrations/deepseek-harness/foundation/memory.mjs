import path from 'node:path';
import { promises as fs } from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { readJson, writeJson } from './state.mjs';

const runtime = createRequire(new URL('../web-runtime/package.json', import.meta.url));
const mcp = await import(pathToFileURL(runtime.resolve('@deepseek-ai/dsh-mcp-client')).href);
const server = runtime.resolve('@modelcontextprotocol/server-memory/dist/index.js');
export class ProjectMemory {
  constructor(ctx, root, onReady) {
    this.ctx = ctx; this.root = root;
    this.onReady = onReady; this.enabled = false;
    this.namespace = 'hzmem_' + createHash('sha256').update(root).digest('hex').slice(0, 16);
    this.settings = path.join(root, '.highzyme', 'memory-settings.json');
    this.file = path.join(root, '.highzyme', 'memory.jsonl');
  }
  async config() { const config = await readJson(this.settings, { enabled: false }); this.enabled = config.enabled; return config; }
  async enable(enabled) { await writeJson(this.settings, { enabled: !!enabled }); const config = await this.config(); this.onReady?.(); return config; }
  async start() {
    this.ready ||= (async () => {
      await fs.mkdir(path.dirname(this.file), { recursive: true });
      await mcp.apply(this.ctx, { serverName: this.namespace, transport: 'stdio', command: process.execPath, args: [server], env: { MEMORY_FILE_PATH: this.file }, cwd: this.root, toolCallTimeoutMs: 15000, failOnStartupError: true });
      this.onReady?.();
    })().catch(e => { this.ready = null; throw e; });
    return this.ready;
  }
  async call(name, args) {
    await this.start();
    const result = await this.ctx.tools.execute({ callId: randomUUID(), name: 'mcp__' + this.namespace + '__' + name, arguments: args, signal: AbortSignal.timeout(20000) });
    if (result.isError) throw new Error(result.error.message);
    const text = result.content.filter(b => b.type === 'text').map(b => b.text).join('\n');
    try { return JSON.parse(text); } catch { return { message: text }; }
  }
  async list(query = '') {
    const graph = await this.call(query ? 'search_nodes' : 'read_graph', query ? { query } : {});
    return (graph.entities || []).filter(e => e.entityType === 'highzyme-project-memory').flatMap(e => {
      try { return [{ id: e.name, ...JSON.parse(e.observations[0]) }]; } catch { return []; }
    });
  }
  async save(input, source = {}) {
    if (!input.title?.trim() || !input.content?.trim()) throw new Error('Enter a memory title and content');
    const existing = input.id ? (await this.list()).find(m => m.id === input.id) : null;
    if (input.id && !existing) throw new Error('Memory not found');
    const id = existing?.id || randomUUID();
    const row = { title: input.title.trim(), content: input.content.trim(), source: existing?.source || source, createdAt: existing?.createdAt || Date.now(), updatedAt: Date.now() };
    if (existing) await this.call('delete_observations', { deletions: [{ entityName: id, observations: [JSON.stringify(Object.fromEntries(Object.entries(existing).filter(([k]) => k !== 'id')))] }] });
    await this.call('create_entities', { entities: [{ name: id, entityType: 'highzyme-project-memory', observations: [JSON.stringify(row)] }] });
    if (existing) await this.call('add_observations', { observations: [{ entityName: id, contents: [JSON.stringify(row)] }] });
    return { id, ...row };
  }
  async remove(id) { await this.call('delete_entities', { entityNames: [id] }); return { removed: true }; }
}
