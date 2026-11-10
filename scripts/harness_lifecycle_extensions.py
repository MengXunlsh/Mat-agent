"""Narrow lifecycle seats over the pinned Harness runtime, regenerated at startup."""

def prepare_lifecycle(runtime):
    file = runtime / 'dsh-api-session-controller/lib/index.js'
    source = file.read_text(encoding='utf-8')
    if 'highzymeOwn(resume, options)' not in source:
        start = source.index('var ApiSessionAgentController = class')
        end = source.index('//#endregion', start)
        section = source[start:end].replace('this.ctx.agents.resume({', 'this.highzymeOwn(true, {').replace('this.ctx.agents.create({', 'this.highzymeOwn(false, {')
        # The presence of a persisted session selects resume without changing preset setup.
        pos = section.index('\n')
        section = section[:pos] + '''
    highzymeHandles = new Map();
    async highzymeOwn(resume, options) {
      const handle = await (resume ? this.ctx.agents.resume(options) : this.ctx.agents.create(options));
      this.highzymeHandles.set(handle.agent.session.id, handle);
      return handle;
    }
    async highzymeDispose(id) {
      const handle = this.highzymeHandles.get(id);
      if (handle) { await handle.dispose(); this.highzymeHandles.delete(id); }
      if (this.ctx.agents.get(id)) throw new Error('Close the active task before deleting this conversation');
    }
''' + section[pos:]
        file.write_text(source[:start] + section + source[end:], encoding='utf-8', newline='\n')
    file = runtime / 'dsh-session-persistence-jsonl/lib/index.js'
    source = file.read_text(encoding='utf-8')
    if 'async highzymeDelete(id)' not in source:
        pos = source.index('\n\tasync list(options)')
        source = source[:pos] + '''
    async highzymeDelete(id) {
      const selected = await this.findLog(id);
      if (!selected) return;
      const handle = await this.open(id, 'write');
      await handle.close();
      const target = dirname(selected.sourcePath);
      if (!resolve(target).startsWith(resolve(this.root) + (process.platform === 'win32' ? '\\\\' : '/'))) throw new Error('Invalid session storage location');
      await rm(target, { recursive: true, force: true });
      this.coldLogMemo.delete(id);
    }
''' + source[pos:]
        file.write_text(source, encoding='utf-8', newline='\n')

    file = runtime / 'dsh-agent/lib/index.js'
    source = file.read_text(encoding='utf-8')
    if 'async highzymeDispose(id)' not in source:
        for method in ['createAgent', 'resume']:
            old = 'return Reflect.apply(target.' + method + ', receiver, [ownerCtx, options]);'
            new = 'const handle = await Reflect.apply(target.' + method + ', receiver, [ownerCtx, options]); this.highzymeHandles ||= new Map(); this.highzymeHandles.set(handle.agent.session.id, handle); return handle;'
            if old not in source: raise RuntimeError('Native agent lifecycle changed')
            source = source.replace(old, new)
        position = source.index('\n\tasync create(options)')
        source = source[:position] + "\n    async highzymeDispose(id) { const handle = this.highzymeHandles?.get(id); if (handle) { await handle.dispose(); this.highzymeHandles.delete(id); } }\n" + source[position:]
        file.write_text(source, encoding='utf-8', newline='\n')
    file = runtime / 'dsh-api-session-controller/lib/index.js'
    source = file.read_text(encoding='utf-8')
    old = "if (this.ctx.agents.get(id)) throw new Error('Close the active task before deleting this conversation');"
    new = "await this.ctx.agents.highzymeDispose(id); if (this.ctx.agents.get(id)) throw new Error('Close the active task before deleting this conversation');"
    if new not in source: file.write_text(source.replace(old, new), encoding='utf-8', newline='\n')

    file = runtime / 'dsh-experimental-worktree/lib/index.js'
    source = file.read_text(encoding='utf-8')
    marker = '"safe.directory=" + directory'
    if marker not in source:
        source = source.replace('this.config.gitCommand,\n', 'this.config.gitCommand,\n            "-c", "safe.directory=" + directory,\n')
        file.write_text(source, encoding='utf-8', newline='\n')

    file = runtime / 'dsh-session-projection-cache/lib/index.js'
    source = file.read_text(encoding='utf-8')
    if 'async highzymeDelete(id)' not in source:
        position = source.index('\n\tasync put(id, identity, rows)')
        source = source[:position] + "\n    highzymeDeleted = new Set();\n    async highzymeDelete(id) { this.highzymeDeleted.add(id); await this.requireTable().delete(id); }\n" + source[position:]
        source = source.replace('async put(id, identity, rows) {', 'async put(id, identity, rows) {\n        if (this.highzymeDeleted.has(id)) return;')
        file.write_text(source, encoding='utf-8', newline='\n')
