export class DefaultModelSettings {
  constructor(ctx) { this.ctx = ctx; }
  async catalog() { return this.ctx.sessionController.modelCatalog(); }
  async save(input) {
    const catalog = await this.catalog();
    if (!catalog.groups.some(group => group.id === input.provider && group.models.some(model => model.id === input.model))) throw new Error('Choose an available connection and model');
    const value = await this.ctx.llm.resolveCallConfig(input);
    const selection = { provider: value.provider, model: value.model, ...(value.reasoningEffort === undefined ? {} : { reasoningEffort: String(value.reasoningEffort) }) };
    await this.ctx.agentDefaultModel.saveSelection(selection);
    return this.catalog();
  }
}
