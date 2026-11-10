import test from 'node:test';
import assert from 'node:assert/strict';
import { DefaultModelSettings } from './default-model.mjs';

test('default selection validates the native catalog and saves only provider, model and reasoning through Harness', async () => {
    let selection = { provider: '', model: '' };
    const groups = [{ id: 'local', models: [{ id: 'model-a' }, { id: 'model-b' }] }];
    const ctx = { sessionController: { modelCatalog: async () => ({ default: selection, groups, failures: [] }) },
      llm: { resolveCallConfig: async value => value }, agentDefaultModel: { saveSelection: async value => { selection = value; } } };
    const settings = new DefaultModelSettings(ctx);
    await assert.rejects(settings.save({ provider: 'other', model: 'model-a' }), /available/);
    const result = await settings.save({ provider: 'local', model: 'model-b', reasoningEffort: 'high', unused: 'excluded' });
    assert.deepEqual(result.default, { provider: 'local', model: 'model-b', reasoningEffort: 'high' });
    assert.equal((await settings.catalog()).default.model, 'model-b');
});
