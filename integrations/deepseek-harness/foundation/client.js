window.__ModuleLoader__.load({
  id: '@highzyme/harness-foundation',
  factory(require) {
    const React = require('react'), h = React.createElement;
    const { useState, useEffect, useCallback, useContext, createContext, useSyncExternalStore, useRef, useMemo } = React;
    const { Button, Input, Modal, Menu, MenuItemButton, SegmentedTabs, DiffBlock, IconRefreshOutlineRegular, IconTrashOutlineRegular } = require('@deepseek-ai/dsh-client-ui-primitives');
    const { ModelSelect } = require('@deepseek-ai/dsh-client-ui-model-selection');
    const { recentWorkspace } = require('@deepseek-ai/dsh-client-ui-workspace');
    const { createSnapshotStore } = require('@deepseek-ai/dsh-client-store');
    const GrantsContext = createContext(null);
    let context, currentSession = '', draftRequest = null, catalog = { projects: [], resources: [], operations: { shell: false, network: false, compute: false }, jobDefaults: {} };
    const listeners = new Set();
    const subscribe = callback => { listeners.add(callback); return () => listeners.delete(callback); };
    const publishCatalog = value => { catalog = value; for (const callback of listeners) callback(); };
    const activeSession = () => Object.values(context.sessions.list.getSnapshot().byId).find(s => s.retainedBy.mainView > 0)?.id || currentSession;
    const projectForNewConversation = (workspaces, sessions, hint) => hint || workspaces.items.find(p => p.sessionIds.includes(activeSession()))?.workspaceId || recentWorkspace(workspaces.items, sessions.byId);
    const zh = {
      hub: '项目面板', cases: '案例', artifacts: '成果', tasks: '任务', versions: '版本', access: 'Agent 访问与权限', accessMenu: '权限管理', projects: '项目与文件', resources: '工具与计算资源', computeTab: '计算资源',
      empty: '请先从左侧打开一个本地项目', folder: '项目文件', newCase: '新建案例', title: '名称', create: '创建', cancel: '取消', save: '保存', open: '打开', rename: '重命名', archive: '归档', trash: '移到回收站', restore: '恢复',
      active: '进行中', archived: '已归档', deleted: '回收站', noCases: '还没有案例。普通会话仍保留在左侧项目中。', start: '开始案例会话', continue: '继续会话', newConversation: '新建案例会话',
      addArtifact: '添加成果', fromConversation: '整理为成果', source: '资料', plan: '方案', result: '结果', code: '代码', data: '数据', file: '项目内文件路径', body: '文档内容', kind: '类型',
      newDocument: '新建文档', existingFile: '已有文件', noArtifacts: '还没有成果，可保存会话结论或登记项目中的文件。', reference: '引用到案例', chooseCase: '选择案例', cited: '已引用', preview: '预览文件',
      references: '引用的成果版本', savedVersion: '已保存版本', latest: '当前版本', noTasks: '当前项目没有任务记录', refresh: '刷新', stop: '停止', noVersions: '尚无版本记录', checkpoint: '保存项目版本', message: '本次完成或修改了什么', changes: '当前文件变更',
      policy: '资料提交给模型', allProject: '整个项目', selected: '指定文件或目录', readPaths: '允许读取的路径（每行一个）', writePaths: '允许修改的路径（每行一个，. 表示整个项目）',
      shell: '允许本地 Shell 与代码执行', network: '允许联网检索与读取', compute: '允许提交外接计算',

      computeHint: '连接你自己的资源并通过检查后，才能开启计算。', noCompute: '尚未接入计算资源。', url: '服务地址', token: '连接令牌', tokenHint: '留空沿用已保存的令牌', addResource: '添加资源', check: '检查连接', enabled: '允许使用此资源', remove: '移除', ready: '已验证', notReady: '未验证',

      localPath: '本机项目目录', search: '检索服务', subagents: '子 Agent', terminal: 'Shell', advanced: '高级', saved: '已保存', running: '运行中', queued: '排队中', completed: '已完成', failed: '失败', killed: '已取消', interrupted: '已中断', unknown: '待核对',
      taskRecheck: '上次记录，点击刷新核对远端状态', project: '项目', projectSelect: '选择项目', projectActions: '项目操作', caseMenu: '案例操作', artifactMenu: '成果操作', useVersion: '引用此版本', referencesEmpty: '尚未引用成果', edit: '编辑', success: '操作完成', versionSaved: '版本已保存', close: '关闭', registered: '成果已保存',
    };
    const en = {
      hub: 'Project panel', cases: 'Cases', artifacts: 'Artifacts', tasks: 'Tasks', versions: 'Versions', access: 'Agent access & permissions', accessMenu: 'Permissions', projects: 'Projects & files', resources: 'Tools & compute', computeTab: 'Compute',
      empty: 'Open a local project from the sidebar first', folder: 'Project files', newCase: 'New case', title: 'Name', create: 'Create', cancel: 'Cancel', save: 'Save', open: 'Open', rename: 'Rename', archive: 'Archive', trash: 'Move to trash', restore: 'Restore',
      active: 'Active', archived: 'Archived', deleted: 'Trash', noCases: 'No cases yet. Ordinary conversations remain in the project sidebar.', start: 'Start case conversation', continue: 'Continue conversation', newConversation: 'New case conversation',
      addArtifact: 'Add artifact', fromConversation: 'Save as artifact', source: 'Source', plan: 'Plan', result: 'Result', code: 'Code', data: 'Data', file: 'Project-relative file path', body: 'Document content', kind: 'Type',
      newDocument: 'New document', existingFile: 'Existing file', noArtifacts: 'Save a conversation outcome or register a project file here.', reference: 'Reference in a case', chooseCase: 'Choose a case', cited: 'Referenced', preview: 'Preview file',
      references: 'Referenced artifact versions', savedVersion: 'Saved version', latest: 'Current version', noTasks: 'No project tasks recorded', refresh: 'Refresh', stop: 'Stop', noVersions: 'No versions recorded', checkpoint: 'Save project version', message: 'Describe the completed task or change', changes: 'Current file changes',
      policy: 'Content sent to the model', allProject: 'Entire project', selected: 'Selected files or folders', readPaths: 'Readable paths (one per line)', writePaths: 'Writable paths (one per line; . means the whole project)',
      shell: 'Allow local Shell and code execution', network: 'Allow web search and reading', compute: 'Allow external compute submissions',

      computeHint: 'Connect your own resource and check it before enabling computation.', noCompute: 'No compute resource connected.', url: 'Service URL', token: 'Connection token', tokenHint: 'Leave blank to keep the saved token', addResource: 'Add resource', check: 'Check connection', enabled: 'Enable this resource', remove: 'Remove', ready: 'Verified', notReady: 'Not verified',

      localPath: 'Local project folder', search: 'Search service', subagents: 'Subagents', terminal: 'Shell', advanced: 'Advanced', saved: 'Saved', running: 'Running', queued: 'Queued', completed: 'Completed', failed: 'Failed', killed: 'Cancelled', interrupted: 'Interrupted', unknown: 'Needs checking',
      taskRecheck: 'Last known state; refresh to check the remote job', project: 'Project', projectSelect: 'Choose project', projectActions: 'Project actions', caseMenu: 'Case actions', artifactMenu: 'Artifact actions', useVersion: 'Reference this version', referencesEmpty: 'No referenced artifacts', edit: 'Edit', success: 'Done', versionSaved: 'Version saved', close: 'Close', registered: 'Artifact saved',
    };
    Object.assign(zh, {
      compareEvidence: '比较证据', replotRates: '调整曲线',
      compareEvidencePrompt: '使用 assay-comparison 技能比较以下证据文件中的测定条件与结果，先读取材料、测定及字段，按我的研究目的比较。',
      replotRatesPrompt: '使用 initial-rate-kinetics 技能读取以下已保存拟合结果，按我的要求调整曲线布局或标签，不重新拟合。',
      readPaper: '阅读文献', checkStructure: '核对结构', fitRates: '拟合初始速率', taskPrepared: '任务已填入对话框', draftOccupied: '请先发送或清空已有草稿',
      readPaperPrompt: '使用 literature-evidence 技能阅读以下项目文件，先概括研究问题、材料、方法与主要结果，保留来源位置。',
      checkStructurePrompt: '使用 material-structure-check 技能核对以下项目结构文件，说明组成和实际结构信息。',
      fitRatesPrompt: '使用 initial-rate-kinetics 技能分析以下项目数据。先查看列名和预览；明确底物浓度、初始速率及单位后，进行 Michaelis-Menten 拟合并保存结果。如有歧义，先询问我。',
      hub: '项目资源', files: '文件', use: '允许使用', modify: '允许修改', useShort: '使用', modifyShort: '修改',
      location: '目录位置', copyPath: '复制路径', discussion: '普通会话', newItem: '新建',
      noCases: '还没有案例', noArtifacts: '还没有成果', start: '打开案例', continue: '打开案例', fromConversation: '整理讨论为成果', saveAnswer: '保存这条回答',
      chooseMessages: '选择整理范围', allMessages: '最近轮次', rounds: '整理轮数', round: '轮', user: '用户', assistant: 'Agent', selectRound: '选择整轮', selectionLimit: '最多选择 15 轮', pendingDraft: '成果草稿待保存', noTasks: '没有待办任务', waiting: '等待处理', pending: '待执行', retry: '重新整理', dismiss: '关闭提示', selectedMessages: '选中的消息', organize: '开始整理', organizing: '正在整理', draft: '查看草稿', sourceSession: '来源会话',
      showChanges: '查看修改', noChanges: '没有文件变更', wrap: '自动换行', nowrap: '取消换行', copy: '复制', copied: '已复制', expand: '展开', collapse: '收起',
      shellLimited: '当前文件或联网限制下，Shell 不可用', saved: '已保存', defaultDirectory: '默认项目位置', newProject: '打开或新建项目', choose: '选择目录',
      advanced: '高级', permissions: '权限', fullProject: '整个项目', selectedOnly: '仅选中的资料', readOnly: '只读', projectWrite: '项目内修改',
      accessMenu: '执行权限', permissionsUpdated: '项目权限已更新', operationsUpdated: '执行权限已更新', fileStem: '英文文件名', destination: '保存位置', manageCases: '管理案例', projectChanges: '项目修改', selectChanges: '选择本次要记录的文件', filePermissions: '文件权限', artifactPermissions: '成果权限',
    });
    Object.assign(en, {
      compareEvidence: 'Compare evidence', replotRates: 'Adjust curves',
      compareEvidencePrompt: 'Use assay-comparison on this evidence file. Read the materials, assays and available fields, then compare conditions and results for my research question.',
      replotRatesPrompt: 'Use initial-rate-kinetics to read this saved fit and adjust curve layout or labels as requested, without refitting.',
      readPaper: 'Read paper', checkStructure: 'Check structure', fitRates: 'Fit initial rates', taskPrepared: 'Task added to the composer', draftOccupied: 'Send or clear the existing draft first',
      readPaperPrompt: 'Use the literature-evidence skill to read this project file. Summarize the question, materials, methods and main results with source locations.',
      checkStructurePrompt: 'Use the material-structure-check skill to check this project structure file and explain its composition and actual structural contents.',
      fitRatesPrompt: 'Use the initial-rate-kinetics skill for this project table. Inspect columns and preview first; establish substrate concentration, initial rate and units, then fit Michaelis-Menten kinetics and save the results. Ask me if the mapping or units are ambiguous.',
      hub: 'Project resources', files: 'Files', use: 'Allow use', modify: 'Allow edits', useShort: 'Use', modifyShort: 'Edit',
      location: 'Folder location', copyPath: 'Copy path', discussion: 'Conversation', newItem: 'New',
      noCases: 'No cases yet', noArtifacts: 'No artifacts yet', start: 'Open case', continue: 'Open case', fromConversation: 'Organize discussion', saveAnswer: 'Save this answer',
      chooseMessages: 'Discussion range', allMessages: 'Recent rounds', rounds: 'Number of rounds', round: 'Round', user: 'User', assistant: 'Agent', selectRound: 'Select round', selectionLimit: 'Select up to 15 rounds', pendingDraft: 'Draft ready to save', noTasks: 'No pending tasks', waiting: 'Waiting', pending: 'Pending', retry: 'Organize again', dismiss: 'Dismiss notice', selectedMessages: 'Selected messages', organize: 'Start organizing', organizing: 'Organizing', draft: 'View draft', sourceSession: 'Source conversation',
      showChanges: 'View changes', noChanges: 'No file changes', wrap: 'Wrap lines', nowrap: 'Unwrap lines', copy: 'Copy', copied: 'Copied', expand: 'Expand', collapse: 'Collapse',
      shellLimited: 'Shell is unavailable with these file or network restrictions', saved: 'Saved', defaultDirectory: 'Default project location', newProject: 'Open or create project', choose: 'Choose folder',
      advanced: 'Advanced', permissions: 'Permissions', fullProject: 'Entire project', selectedOnly: 'Selected sources only', readOnly: 'Read only', projectWrite: 'Project write',
      accessMenu: 'Execution permissions', permissionsUpdated: 'Project permissions updated', operationsUpdated: 'Execution permissions updated', fileStem: 'English filename', destination: 'Save location', manageCases: 'Manage cases', projectChanges: 'Project changes', selectChanges: 'Select files to record', filePermissions: 'File permissions', artifactPermissions: 'Artifact permissions',
    });
    Object.assign(zh, { archiveManager: '归档', permanentDelete: '永久删除', deleteFiles: '同时删除案例文件夹', deleteNotice: '会话记录将永久删除，已整理的项目成果保留。Git 历史不受影响。', archiveEmpty: '没有归档项目', find: '搜索名称', memory: '记忆', memorySearch: '搜索', memoryEnabled: '启用项目记忆', addMemory: '添加记忆', memoryEmpty: '还没有项目记忆', restoreVersion: '恢复到此版本', undoChange: '撤销这次修改', confirmRestore: '确认恢复', restorePreview: '恢复预览', binary: '二进制文件，请查看对应文件版本', workarea: '独立工作区', createWorkarea: '在独立工作区继续', workareaName: '工作区名称（英文关键词）', mainWorkspace: '项目目录', compare: '比较改动', merge: '合并回项目', removeWorkarea: '移除独立工作区', enterWorkarea: '进入独立工作区', selectAll: '全选', sourceDeleted: '来源记录已删除', selectFiles: '选择要恢复的文件', unownedChanges: '选择属于本次任务的文件', memorySource: '来源', memoryDelete: '删除这条记忆？', mergeConfirm: '将已保存的改动合并回项目？', removeConfirm: '移除已合并的独立工作区？' });
    Object.assign(en, { archiveManager: 'Archive', permanentDelete: 'Delete permanently', deleteFiles: 'Also delete the case folder', deleteNotice: 'Conversation records will be deleted permanently. Published artifacts and Git history are retained.', archiveEmpty: 'No archived items', find: 'Search names', memory: 'Memory', memorySearch: 'Search', memoryEnabled: 'Enable project memory', addMemory: 'Add memory', memoryEmpty: 'No project memories yet', restoreVersion: 'Restore this version', undoChange: 'Undo this change', confirmRestore: 'Confirm restoration', restorePreview: 'Restoration preview', binary: 'Binary file; inspect the file version', workarea: 'Independent workspace', createWorkarea: 'Continue in an independent workspace', workareaName: 'Workspace name (English keywords)', mainWorkspace: 'Project folder', compare: 'Compare changes', merge: 'Merge into project', removeWorkarea: 'Remove independent workspace', enterWorkarea: 'Enter independent workspace', selectAll: 'Select all', sourceDeleted: 'Source record deleted', selectFiles: 'Select files to restore', unownedChanges: 'Select files belonging to this task', memorySource: 'Source', memoryDelete: 'Delete this memory?', mergeConfirm: 'Merge the saved changes into the project?', removeConfirm: 'Remove the merged independent workspace?' });
    Object.assign(zh, { relatedFiles: '相关文件', analyzeSignal: '信号分析', measureColor: '图像比色', fileAnalysis: '分析数据',
      analyzeSignalPrompt: '使用 signal-analysis 技能分析以下表格，先检查数据列，再按我的研究目的选择标定或信号分析。',
      measureColorPrompt: '使用 image-colorimetry 技能检查以下图像，选择合适的取样区域并保存颜色测量结果。',
      replotRatesPrompt: '读取以下已保存分析结果，按我的要求调整曲线布局或标签，使用对应的重绘工具，不重新计算数值。' });
    Object.assign(en, { relatedFiles: 'Related files', analyzeSignal: 'Analyze signal', measureColor: 'Image colorimetry', fileAnalysis: 'Analyze data',
      analyzeSignalPrompt: 'Use signal-analysis to inspect this table and choose the calibration or readout analysis for my question.',
      measureColorPrompt: 'Use image-colorimetry to inspect this image, choose a suitable sampling region and save the color measurements.',
      replotRatesPrompt: 'Read this saved analysis and adjust the curve layout or labels using its corresponding replot tool, without recalculating numerical results.' });
    Object.assign(zh, { reviseAnalysis: '修订分析', newAnalysis: '另建分析', pinnedVersion: '已引用版本', currentArtifact: '查看当前成果', updateReference: '更新引用',
      reviseAnalysisPrompt: '修订下面这项分析，保留原成果并记录修改。请先读取输入设置和相关结果，再按我接下来的要求调整。',
      newAnalysisPrompt: '基于下面这项成果另建一项独立分析，保留原来的成果和文件。请先读取输入设置和来源，再按我接下来的要求调整。' });
    Object.assign(en, { reviseAnalysis: 'Revise analysis', newAnalysis: 'New independent analysis', pinnedVersion: 'Referenced version', currentArtifact: 'Open current artifact', updateReference: 'Update reference',
      reviseAnalysisPrompt: 'Revise the analysis below in place and record the changes. Inspect its input settings and relevant results, then follow the changes I specify next.',
      newAnalysisPrompt: 'Create an independent analysis based on this artifact, preserving the original result and files. Inspect its input settings and sources, then follow the changes I specify next.' });
    Object.assign(zh, { collectingResult: '正在取回结果', collectFailed: '结果取回失败' });
    Object.assign(en, { collectingResult: 'Retrieving result', collectFailed: 'Result retrieval failed' });
    Object.assign(zh, { connectCompute: '连接计算资源', sshResource: 'SSH / Slurm', httpResource: '计算服务', host: '主机或 SSH 别名', port: '端口', username: '用户名', privateKey: '私钥文件', selectKey: '选择密钥', sshConfigHint: '使用已有 SSH 配置时可留空', inspectEnvironment: '检查环境', connected: '已连接', environmentReady: '环境就绪', environmentMissing: '环境待配置', remoteRoot: '远端工作目录', partition: '队列', account: '计算账号', qos: 'QoS', qeModule: 'QE 软件模块', qeCommand: 'QE 程序', setupScript: '运行环境', pythonCommand: 'Python 程序', mpiCommand: 'MPI 启动器', automatic: '使用当前环境', lastCalculation: '最近计算', calculationPassed: '计算已收敛', calculationFailed: '计算未收敛', collectResult: '取回结果', pendingSetup: '待检查', connection: '连接', computeDetails: '环境与任务设置', testCalculation: '最小计算测试' });
    Object.assign(en, { connectCompute: 'Connect compute resource', sshResource: 'SSH / Slurm', httpResource: 'Compute service', host: 'Host or SSH alias', port: 'Port', username: 'Username', privateKey: 'Private-key file', selectKey: 'Choose key', sshConfigHint: 'Leave blank to use existing SSH configuration', inspectEnvironment: 'Inspect environment', connected: 'Connected', environmentReady: 'Environment ready', environmentMissing: 'Environment needs configuration', remoteRoot: 'Remote working directory', partition: 'Partition', account: 'Account', qos: 'QoS', qeModule: 'QE module', qeCommand: 'QE executable', setupScript: 'Environment setup', pythonCommand: 'Python executable', mpiCommand: 'MPI launcher', automatic: 'Use current environment', lastCalculation: 'Last calculation', calculationPassed: 'Calculation converged', calculationFailed: 'Calculation not converged', collectResult: 'Retrieve result', pendingSetup: 'Not checked', connection: 'Connection', computeDetails: 'Environment and job settings', testCalculation: 'Minimal calculation test' });
    Object.assign(zh, { setupAssistant: '配置助手', continueSetup: '继续配置', submissionReady: '可提交任务', submissionUnavailable: '暂不能提交', qeAvailable: 'QE 可用', qeUnavailable: 'QE 未配置', jobDefaults: '默认任务规格', jobLimits: '任务上限', ranks: 'MPI 进程数', threads: '每进程线程数', memory_mb: '总内存 (MiB)', timeout_seconds: '时限 (秒)', noLimit: '不另设上限', prepared: '待提交', submitting: '正在提交', submission_unknown: '提交待核对', inspectInput: '查看输入', submitCalculation: '提交计算', discard: '取消准备', executionLocation: '执行位置', localExecution: '本机', elapsed: '运行时长', queueReason: '排队原因', failureReason: '失败原因', checkSubmission: '核对提交状态', submissionHelp: '提交结果尚未确认，请先核对状态，不要重复提交。', computeSetupPrompt: '请使用 compute-resource-setup 技能帮助我配置计算资源。先查看已有配置，只询问缺少的信息，检查连接、队列和软件环境，保存配置与默认规格。此次只进行环境配置，不提交计算。请用中文与我交流。', resumeSetupPrompt: '请继续配置下面的计算资源，检查当前环境并解决尚未完成的配置。只进行环境配置，不提交计算。请用中文与我交流。' });
    Object.assign(en, { setupAssistant: 'Setup assistant', continueSetup: 'Continue setup', submissionReady: 'Ready to submit', submissionUnavailable: 'Submission unavailable', qeAvailable: 'QE available', qeUnavailable: 'QE not configured', jobDefaults: 'Default job request', jobLimits: 'Job limits', ranks: 'MPI ranks', threads: 'Threads per rank', memory_mb: 'Total memory (MiB)', timeout_seconds: 'Time limit (seconds)', noLimit: 'No additional limit', prepared: 'Ready for review', submitting: 'Submitting', submission_unknown: 'Submission needs checking', inspectInput: 'Inspect input', submitCalculation: 'Submit calculation', discard: 'Discard preparation', executionLocation: 'Runs on', localExecution: 'This computer', elapsed: 'Elapsed', queueReason: 'Queue reason', failureReason: 'Failure reason', checkSubmission: 'Check submission status', submissionHelp: 'Submission is unconfirmed. Check its status before taking further action; do not resubmit.', computeSetupPrompt: 'Use the compute-resource-setup skill to help me configure a compute resource. Inspect existing profiles, ask only for missing information, check the connection, queues and software, and save the profile and default resource request. Configure the environment only; do not submit any calculation. Respond in English.', resumeSetupPrompt: 'Continue setting up the compute resource below. Check the current environment and resolve incomplete settings. Configure the environment only; do not submit calculations. Respond in English.' });
    const readActions = new Set(['state', 'project.detail', 'project.tasks', 'project.diff', 'project.restorePreview', 'artifact.read', 'artifact.path', 'artifact.file', 'artifact.visual', 'artifact.media', 'artifact.draft', 'case.research', 'model.catalog', 'memory.list', 'workarea.compare']);
    const requests = new Map();
    const api = (action, values = {}) => {
      const key = readActions.has(action) ? JSON.stringify([action, values]) : null;
      if (key && requests.has(key)) return requests.get(key);
      const pending = requestApi(action, values).finally(() => { if (key) requests.delete(key); });
      if (key) requests.set(key, pending);
      return pending;
    };
    const requestApi = async (action, values) => {
      const result = await fetch('api/highzyme', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, ...values }) });
      const body = await result.json(); if (!result.ok) throw new Error(body.error || String(result.status)); return body;
    };
    Object.assign(zh, { calculationStages: '计算步骤', calculationCompleted: '计算流程已完成', convergence: '参数收敛', adsorption: '吸附与结合能', 'formation-energy': '缺陷与位点稳定性', 'electronic-structure': '电子结构', 'charge-analysis': '电荷分析', 'reaction-energy': '反应能与自由能', neb: '反应路径与势垒', method: '计算方法' });
    Object.assign(en, { calculationStages: 'Calculation stages', calculationCompleted: 'Workflow completed', convergence: 'Parameter convergence', adsorption: 'Adsorption and binding', 'formation-energy': 'Defect and site stability', 'electronic-structure': 'Electronic structure', 'charge-analysis': 'Charge analysis', 'reaction-energy': 'Reaction energy and free energy', neb: 'Reaction path and barrier', method: 'Calculation method' });
    Object.assign(zh, { loading: '加载中', origin: '来源', researchWorkflow: '研究流程', workflowKind: '研究类型', general: '通用研究', 'application-exploration': '应用方向探索', 'material-design': '材料候选设计', researchObjective: '研究目标', researchRequirements: '关键要求', prepareResearch: '准备研究任务', objective: '明确目标', evidence: '证据整理', applications: '应用方向', designs: '材料设计', review: '核查与筛选', validation: '验证与反馈', analysis: '研究分析', report: '成果整理', noCandidates: '尚无候选', proposed: '已提出', needs_evidence: '待补证据', needs_information: '待补信息', ready_for_validation: '待验证', rejected: '已排除', reviewed: '已核查', needs_revision: '待修订', hypothesis: '假设', baseline: '对照', uncertainties: '待明确信息', prepareResearchPrompt: '继续当前案例的研究流程。先读取已保存的研究计划、候选和引用的成果，加载对应技能，围绕以下研究目标推进本次需要完成的工作。保留证据和假设的区别，使用已有工具保存候选及成果。外接计算只在所需资源已接通并允许时执行。' });
    Object.assign(en, { loading: 'Loading', origin: 'Source', researchWorkflow: 'Research workflow', workflowKind: 'Research type', general: 'General research', 'application-exploration': 'Application exploration', 'material-design': 'Material candidate design', researchObjective: 'Research objective', researchRequirements: 'Key requirements', prepareResearch: 'Prepare research task', objective: 'Define objective', evidence: 'Gather evidence', applications: 'Application directions', designs: 'Material designs', review: 'Review and screening', validation: 'Validation and feedback', analysis: 'Research analysis', report: 'Report', noCandidates: 'No candidates yet', proposed: 'Proposed', needs_evidence: 'Needs evidence', needs_information: 'Needs information', ready_for_validation: 'Ready for validation', rejected: 'Rejected', reviewed: 'Reviewed', needs_revision: 'Needs revision', hypothesis: 'Hypothesis', baseline: 'Baseline', uncertainties: 'Open questions', prepareResearchPrompt: 'Continue the active case research workflow. Read the saved research plan, candidates and referenced artifacts, load the matching skill, and advance the work requested for the objective below. Distinguish evidence from hypotheses and save candidates and results with existing tools. Execute external computation only with an enabled compatible user resource.' });
    Object.assign(zh, { candidates: '候选', filterAny: '不限', reviewed: '已有反馈', compositionChecks: '组成检查', formula: '组成式', stoichiometry: '计量关系', charge_balance: '电荷平衡', pass: '通过', fail: '不通过', unknown: '未知', netCharge: '净电荷', supports: '支持', contradicts: '矛盾', inconclusive: '尚不能判断' });
    Object.assign(en, { candidates: 'Candidates', filterAny: 'Any', reviewed: 'Feedback recorded', compositionChecks: 'Composition checks', formula: 'Formula', stoichiometry: 'Stoichiometry', charge_balance: 'Charge balance', pass: 'Pass', fail: 'Fail', unknown: 'Unknown', netCharge: 'Net charge', supports: 'Supports', contradicts: 'Contradicts', inconclusive: 'Inconclusive' });
    Object.assign(zh, { stage_objective: '明确目标', stage_evidence: '证据整理', stage_applications: '应用方向', stage_designs: '材料设计', stage_review: '核查与筛选', stage_validation: '验证与反馈', stage_analysis: '研究分析', stage_report: '成果整理' });
    Object.assign(en, { stage_objective: 'Define objective', stage_evidence: 'Gather evidence', stage_applications: 'Application directions', stage_designs: 'Material designs', stage_review: 'Review and screening', stage_validation: 'Validation and feedback', stage_analysis: 'Research analysis', stage_report: 'Report' });
    Object.assign(zh, { proposalStatus: '方案状态', validationOutcome: '验证结论', proposalVersion: '方案版本', not_validated: '未验证', previousProposal: '对应旧方案', unrecordedVersion: '未记录方案版本', basedOnApplication: '承接应用', selectedCandidate: '本次研究对象', allCandidates: '整个案例', linkedValidations: '验证任务与结果', validationQuestion: '验证问题', validationCriterion: '判断依据', ready_for_validation: '可安排验证' });
    Object.assign(en, { proposalStatus: 'Proposal status', validationOutcome: 'Validation outcome', proposalVersion: 'Proposal version', not_validated: 'Not validated', previousProposal: 'Earlier proposal', unrecordedVersion: 'Proposal version unrecorded', basedOnApplication: 'Based on application', selectedCandidate: 'Research target', allCandidates: 'Whole case', linkedValidations: 'Validation tasks and results', validationQuestion: 'Validation question', validationCriterion: 'Decision criterion', ready_for_validation: 'Ready to test' });
    const changed = () => window.dispatchEvent(new Event('highzyme:change'));
    function panelPreferences(projectId) {
      try { return JSON.parse(localStorage.getItem('highzyme.panel.' + projectId) || '{}'); }
      catch { return {}; }
    }
    function savePanelPreferences(projectId, values) {
      localStorage.setItem('highzyme.panel.' + projectId, JSON.stringify({ ...panelPreferences(projectId), ...values }));
    }
    function useData(sessionId = currentSession) {
      const state = useSyncExternalStore(subscribe, () => catalog), [detail, setDetail] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false), [notice, setNotice] = useState('');
      const detailRef = useRef(detail); detailRef.current = detail;
      const project = state.projects.find(p => p.sessions.includes(sessionId));
      const id = project?.id || '';
      const refresh = useCallback(async ({ reloadCatalog = false, jobsOnly = false } = {}) => {
        try {
          const known = catalog.projects.find(p => p.sessions.includes(sessionId));
          if (jobsOnly && known) {
            const value = await api('project.tasks', { projectId: known.id, sessionId });
            if (value.jobs.some(job => job.artifactId && !detailRef.current?.artifacts.some(a => a.id === job.artifactId))) return refresh();
            setDetail(previous => previous && previous.id === known.id ? { ...previous, jobs: value.jobs } : previous);
            return;
          }
          const next = reloadCatalog || !known ? await api('state') : catalog;
          if (next !== catalog) publishCatalog(next);
          const p = next.projects.find(p => p.sessions.includes(sessionId));
          setDetail(p ? await api('project.detail', { projectId: p.id, sessionId }) : null);
        } catch (e) { setError(e.message); }
      }, [sessionId]);
      useEffect(() => { refresh(); const update = () => refresh({ reloadCatalog: true }); window.addEventListener('highzyme:change', update); return () => window.removeEventListener('highzyme:change', update); }, [refresh]);
      useEffect(() => { if (!notice) return; const timer = setTimeout(() => setNotice(''), 2400); return () => clearTimeout(timer); }, [notice]);
      const act = async (action, values, message) => {
        const mutates = typeof action === 'function' ? values?.refresh !== false : !readActions.has(action);
        if (mutates) setBusy(true); setError(''); setNotice('');
        try { const result = typeof action === 'function' ? await action() : await api(action, { projectId: id, sessionId, ...values }); if (mutates) await refresh({ reloadCatalog: /^(case\.|project\.open|workarea\.)/.test(action) }); if (message) setNotice(message); return result; }
        catch (e) { setError(e.message); return null; } finally { if (mutates) setBusy(false); }
      };
      return { state, id, project, sessionId, detail, error, busy, notice, act, refresh };
    }
    const button = (text, onClick, disabled = false, primary = false) => h(Button, { variant: primary ? 'primary' : 'outline', size: 'sm', onClick: event => { const menu = event.currentTarget.closest('details.hz-menu'); if (menu) menu.open = false; return onClick(event); }, disabled, className: 'hz-native-button' }, text);
    const refreshButton = (onClick, disabled, t) => h(Button, { variant: 'ghost', size: 'sm', onClick, disabled, title: t('refresh'), 'aria-label': t('refresh') }, h(IconRefreshOutlineRegular, {}));
    Object.assign(zh, { temperature_C: '温度 (°C)' });
    Object.assign(en, { temperature_C: 'Temperature (°C)' });
    const field = (label, node) => h('label', { className: 'hz-field' }, h('span', null, label), node);
    const input = (value, onChange, extra = {}) => h(Input, { value, onChange: e => onChange(e.target.value), ...extra });
    const option = (value, label) => h('option', { key: value, value }, label);
    const note = text => h('p', { className: 'hz-note' }, text);
    const stamp = date => new Date(date).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    Object.assign(zh, { overview: '查看成果', report: '打开报告', figures: '图表', measurements: '测量数据', parameters: '参数', residuals: '残差', fit: '拟合曲线', curve: '曲线', calibration: '标定曲线', composition: '元素组成', evidence: '文献证据', comparison: '条件比较', formulation: '配方', 'ionic-steps': '离子步', 'scf-energy_Ry': 'SCF 能量', 'scf-accuracy_Ry': 'SCF 收敛', structures: '结构', unitCell: '晶胞', resetView: '复位视图', atoms: '原子', loading: '加载中', previous: '上一页', next: '下一页', sourceFiles: '来源与文件', conditions: '条件', status: '状态', converged: '已收敛', not_converged: '未收敛', 'SCF converged': 'SCF 已收敛', Energy: '能量', Formula: '化学式', materials: '材料', assays: '测定', facts: '证据', group: '分组', concentration_unit: '浓度单位', rate_unit: '速率单位', conditions: '条件', material: '材料', version: '版本', assay: '测定', value: '数值', unit: '单位', review: '核查状态', sources: '来源', field: '字段', state: '状态', role: '作用', parameter: '参数', element: '元素', count: '数量', mass_fraction: '质量分数', signal: '信号', concentration: '浓度', within_calibration_range: '位于标定范围', matched: '一致', different: '不同', missing: '缺失', supported: '已核对', unreviewed: '未核对', needs_review: '待核对', unit_mismatch: '单位不同', 'Outside calibration range': '超出标定范围', 'Input structure': '输入结构', 'Final structure': '最终结构', structureViewer: '结构视图', dimension2: '二维分子结构', sigma: '速率标准差', yes: '是', no: '否', allRows: '全部行', regions: '区域', image: '图像', rgb: 'RGB 均值', hsv: 'HSV 均值', files: '全部文件', rawOutput: '原始输出', inputs: '输入', tables: '数据表', scripts: '分析代码', images: '图件', documents: '文档', configuration: '参数文件', otherFiles: '其他文件' });
    Object.assign(en, { overview: 'View result', report: 'Open report', figures: 'Figures', measurements: 'Measurements', parameters: 'Parameters', residuals: 'Residuals', fit: 'Fitted curve', curve: 'Curve', calibration: 'Calibration', composition: 'Composition', evidence: 'Literature evidence', comparison: 'Condition comparison', formulation: 'Formulation', 'ionic-steps': 'Ionic steps', 'scf-energy_Ry': 'SCF energy', 'scf-accuracy_Ry': 'SCF convergence', structures: 'Structures', unitCell: 'Unit cell', resetView: 'Reset view', atoms: 'Atoms', loading: 'Loading', previous: 'Previous', next: 'Next', sourceFiles: 'Sources & files', conditions: 'Conditions', structureViewer: 'Structure', dimension2: '2D molecular graph', yes: 'Yes', no: 'No', regions: 'Regions', image: 'Image', rgb: 'Mean RGB', hsv: 'Mean HSV', rawOutput: 'Raw output', inputs: 'Inputs', tables: 'Data tables', scripts: 'Analysis code', images: 'Figures', documents: 'Documents', configuration: 'Parameters', otherFiles: 'Other files' });
    Object.assign(zh, { 'Molar mass': '摩尔质量', 'Formal charge': '形式电荷', Components: '组分数', mean_r: 'R 均值', mean_g: 'G 均值', mean_b: 'B 均值', mean_h: 'H 均值', mean_s: 'S 均值', mean_v: 'V 均值', pixels: '像素数', region: '区域', file: '文件', slope: '斜率', intercept: '截距', r_squared: 'R²', km_se: 'SE(Km)', vmax_se: 'SE(Vmax)', observations: '观测数', within_range: '范围内数量', measured_regions: '测量区域数', hsv_scale: 'HSV 量程', operation: '操作', dilution: '稀释', network: '反应网络', fit_calibration: '线性标定', quantify: '样品定量', true: '是', false: '否', inputStructure: '输入结构', finalStructure: '最终结构', 'Estimated SCF accuracy (Ry)': '估计 SCF 误差 (Ry)', 'Total energy (Ry)': '总能量 (Ry)', 'Electronic iteration': '电子迭代步', residual: '残差', fitted_rate: '拟合速率', initial_rate: '初始速率' });
    Object.assign(zh, { km: 'Km', vmax: 'Vmax', rmse: 'RMSE', context: '测定条件', intended_variable: '目标变量', temperature: '温度', activity: '活性', substrate: '底物', x_unit: '浓度单位', y_unit: '信号单位', time_s: '时间 (s)', fitted_signal: '拟合信号', concentration: '浓度', images: '图像' });
    Object.assign(zh, { filterRows: '搜索表格', assumed: '假设参数', reported: '文献参数', derived: '推导参数', km_mM: 'Km (mM)', vmax_uM_s: 'Vmax (μM/s)', cellAtoms: '原胞原子', displayedAtoms: '显示原子' });
    Object.assign(en, { filterRows: 'Search table', cellAtoms: 'Cell atoms', displayedAtoms: 'Displayed atoms' });
    Object.assign(en, { status: 'Status', converged: 'Converged', not_converged: 'Not converged', parameters: 'Parameters', group: 'Group',
      km: 'Km', vmax: 'Vmax', km_se: 'SE(Km)', vmax_se: 'SE(Vmax)', r_squared: 'R²', rmse: 'RMSE', concentration_unit: 'Concentration unit', rate_unit: 'Rate unit',
      material: 'Material', version: 'Version', assay: 'Assay', field: 'Field', value: 'Value', unit: 'Unit', review: 'Review', sources: 'Sources', state: 'State', role: 'Role',
      matched: 'Matched', different: 'Different', missing: 'Missing', supported: 'Checked', unreviewed: 'Unchecked', needs_review: 'Needs review', unit_mismatch: 'Unit mismatch', context: 'Assay conditions', intended_variable: 'Varied condition',
      materials: 'Materials', assays: 'Assays', facts: 'Facts', images: 'Images', measured_regions: 'Measured regions', observations: 'Observations', within_range: 'Within range',
      file: 'File', region: 'Region', pixels: 'Pixels', mean_r: 'Mean R', mean_g: 'Mean G', mean_b: 'Mean B', mean_h: 'Mean H', mean_s: 'Mean S', mean_v: 'Mean V',
      signal: 'Signal', concentration: 'Concentration', within_calibration_range: 'Within calibration range', fitted_signal: 'Fitted signal', residual: 'Residual', initial_rate: 'Initial rate', fitted_rate: 'Fitted rate', time_s: 'Time (s)',
      parameter: 'Parameter', element: 'Element', count: 'Count', mass_fraction: 'Mass fraction', assumed: 'Assumed parameter', reported: 'Reported parameter', derived: 'Derived parameter' });
    const visualLibraries = {};
    function loadVisualLibrary(name, globalName) {
      if (window[globalName]) return Promise.resolve(window[globalName]);
      if (!visualLibraries[name]) visualLibraries[name] = new Promise((resolve, reject) => {
        const script = document.createElement('script'); script.src = '/api/highzyme-assets/' + name;
        script.onload = () => resolve(window[globalName]);
        script.onerror = () => { delete visualLibraries[name]; script.remove(); reject(new Error('Unable to load ' + name)); };
        document.head.append(script);
      });
      return visualLibraries[name];
    }
    function warmVisualLibraries(artifact) {
      const operation = artifact.analysis?.operation || '';
      if (/quantum-espresso|fit_kinetics|replot_kinetics|calculation:(signal|reaction|calibration)/.test(operation)) loadVisualLibrary('echarts', 'echarts').catch(() => {});
      if ((artifact.relatedFiles || [artifact.file]).some(file => /\.(cif|mmcif|pdb|xyz|extxyz|vasp)$/i.test(file))) loadVisualLibrary('molecule', '$3Dmol').catch(() => {});
    }
    const displayNumber = value => typeof value === 'number' ? (Number.isInteger(value) ? String(value) : Number(value.toPrecision(6)).toString()) : value === null || value === undefined || value === '' ? '—' : String(value);
    Object.assign(zh, { densityIsosurface: '差分电荷等值面', densityColors: '橙色：电子积累；蓝色：电子减少', calculationCompleted: '计算已完成', convergence: '参数收敛', 'energy-comparison': '能量比较', dos: '态密度', pdos: '投影态密度', bands: '能带', 'charge-difference': '差分电荷', 'neb-path': '反应路径', 'density-of-states': '态密度数据', 'band-centers': '轨道中心', 'planar-charge': '平面平均电荷', sample: '序号', energy_eV: '能量 (eV)', delta_eV_atom: '相对能量 (eV/原子)', energy_relative_eV: '相对能量 (eV)', label: '名称', coefficients: '组合系数', electronic_eV: '电子能 (eV)', thermal_correction_eV: '热校正 (eV)', band: '能带', path: '路径坐标', distance_A: '距离 (Å)', density_e_A3: '电荷密度 (e/Å³)', atom: '原子序号', partition_electrons: '分区电子数', reference_electrons: '参考电子数', net_charge_e: '净电荷 (e)', image: '路径图像', coordinate: '归一化路径坐标', force_error_eV_A: '力误差 (eV/Å)', center_relative_eV: '相对轨道中心 (eV)', window_eV: '积分窗口 (eV)', orbital: '轨道' });
    Object.assign(en, { densityIsosurface: 'Difference-density isosurface', densityColors: 'Orange: electron accumulation; blue: electron depletion', calculationCompleted: 'Calculation completed', convergence: 'Parameter convergence', 'energy-comparison': 'Energy comparison', dos: 'Density of states', pdos: 'Projected DOS', bands: 'Band structure', 'charge-difference': 'Charge-density difference', 'neb-path': 'Reaction path', 'density-of-states': 'DOS data', 'band-centers': 'Orbital centers', 'planar-charge': 'Planar charge density', energy_eV: 'Energy (eV)', delta_eV_atom: 'Relative energy (eV/atom)', energy_relative_eV: 'Relative energy (eV)', electronic_eV: 'Electronic energy (eV)', thermal_correction_eV: 'Thermal correction (eV)', distance_A: 'Distance (Å)', density_e_A3: 'Charge density (e/Å³)', net_charge_e: 'Net charge (e)', force_error_eV_A: 'Force error (eV/Å)' });
    Object.assign(zh, { energy_reference: '能量参考', fermi: '费米能级', vbm: '价带顶', dos_up: '态密度 ↑ (states/eV)', dos_down: '态密度 ↓ (states/eV)' });
    Object.assign(en, { energy_reference: 'Energy reference', fermi: 'Fermi level', vbm: 'Valence-band maximum', dos_up: 'DOS ↑ (states/eV)', dos_down: 'DOS ↓ (states/eV)' });
    Object.assign(zh, { caseFolder: '目录关键词（可选）' });
    Object.assign(en, { caseFolder: 'Folder keywords (optional)' });
    Object.assign(zh, { defaultModel: '新会话默认模型', modelRequired: '请先选择模型，或在设置中选择新会话默认模型。' });
    Object.assign(zh, { createFailed: '创建失败，请重试。', projectLoadFailed: '项目列表加载失败。', projectDirectoryUnavailable: '项目目录不可用，请检查目录是否存在且可读写。', failureDetails: '查看详情' });
    Object.assign(en, { createFailed: 'Could not create the conversation. Try again.', projectLoadFailed: 'Could not load projects.', projectDirectoryUnavailable: 'The project folder is unavailable. Check that it exists and is readable and writable.', failureDetails: 'Show details' });
    Object.assign(zh, { openingSetup: '正在打开配置助手…', setupBusy: '配置会话正在处理任务，请等待完成或先停止。' });
    Object.assign(en, { openingSetup: 'Opening setup assistant…', setupBusy: 'The setup conversation is busy. Wait for it to finish or stop the current task.' });
    Object.assign(en, { defaultModel: 'Default model for new conversations', modelRequired: 'Choose a model, or set a default model in Settings.' });
    function ScientificChart({ plot, t }) {
      const element = useRef(null), [error, setError] = useState('');
      useEffect(() => {
        let disposed = false, chart, observer;
        loadVisualLibrary('echarts', 'echarts').then(library => {
          if (disposed) return;
          chart = library.init(element.current, null, { renderer: 'svg' });
          const colors = plot.palette;
          const categorical = plot.id === 'energy-comparison';
          const axisNameStyle = { rich: { ref: { fontSize: 9, padding: [7, 0, 0, 0] } } };
          const symbols = ['circle', 'rect', 'triangle', 'diamond', 'pin'];
          const series = plot.series.map((s, i) => {
            const index = s.color_index ?? i, color = colors[index % colors.length];
            return { name: s.label, type: s.style === 'points' ? 'scatter' : 'line', symbol: symbols[index % symbols.length], symbolSize: 7,
              showSymbol: s.style === 'points', connectNulls: false, clip: true,
              data: s.x.map((x, j) => [categorical ? plot.x_ticks.labels[j] : x, s.y[j]]), itemStyle: { color }, lineStyle: { color, width: 2, type: ['solid', 'dashed', 'dotted'][index % 3] },
              markLine: i === 0 ? { silent: true, symbol: 'none', label: { position: 'insideEndTop' }, data: [
                ...(plot.zero_line || plot.threshold ? [{ [plot.zero_axis === 'x' ? 'xAxis' : 'yAxis']: plot.threshold || 0, label: { formatter: plot.threshold ? 'SCF tolerance = ' + plot.threshold : '0' } }] : []),
                ...(plot.x_ticks && !categorical ? plot.x_ticks.positions.map((x, j) => ({ xAxis: x, label: { formatter: plot.x_ticks.labels[j], position: 'start' }, lineStyle: { type: 'solid', opacity: .4 } })) : [])
              ], lineStyle: { color: '#7b899b', type: 'dashed' } } : undefined };
          });
          if (plot.threshold) {
            const x = plot.series.flatMap(s => s.x);
            series.push({ name: 'SCF tolerance', type: 'line', symbol: 'none', silent: true, data: [[Math.min(...x), plot.threshold], [Math.max(...x), plot.threshold]], itemStyle: { color: '#6F747B' }, lineStyle: { color: '#6F747B', type: 'dashed', width: 1.5 } });
          }
          plot.series.forEach((s, i) => {
            if (!s.error) return;
            series.push({ name: s.label, type: 'custom', silent: true, tooltip: { show: false },
              data: s.x.map((x, j) => [x, s.y[j] - s.error[j], s.y[j] + s.error[j]]),
              renderItem: (params, api) => { const a = api.coord([api.value(0), api.value(1)]), b = api.coord([api.value(0), api.value(2)]); return { type: 'group', children: [[a[0], a[1], b[0], b[1]], [a[0]-3, a[1], a[0]+3, a[1]], [b[0]-3, b[1], b[0]+3, b[1]]].map(p => ({ type: 'line', shape: { x1: p[0], y1: p[1], x2: p[2], y2: p[3] }, style: { stroke: colors[(s.color_index ?? i) % colors.length], lineWidth: 1 } })) }; } });
          });
          chart.setOption({ animation: false, textStyle: { fontFamily: 'Arial, sans-serif', fontSize: 12, color: '#344054' },
            tooltip: { trigger: 'item', renderMode: 'richText', valueFormatter: displayNumber },
            legend: { show: plot.legend !== false, type: 'scroll', top: 4, data: [...new Set(plot.series.map(s => s.label)), ...(plot.threshold ? ['SCF tolerance'] : [])] },
            grid: { left: 84, right: 28, top: plot.legend === false ? 24 : 48, bottom: 64 },
            xAxis: { type: categorical ? 'category' : 'value', ...(categorical ? { data: plot.x_ticks.labels } : {}), name: plot.x_rich || plot.x_label, nameTextStyle: axisNameStyle, nameLocation: 'middle', nameGap: 36, scale: true, splitLine: { show: false }, axisLabel: { show: categorical || !plot.x_ticks, formatter: categorical ? undefined : displayNumber, hideOverlap: true } },
            yAxis: { type: plot.y_scale || 'value', name: plot.y_rich || plot.y_label, nameTextStyle: axisNameStyle, nameLocation: 'middle', nameGap: 62, scale: true, splitLine: { lineStyle: { color: '#eef1f5' } }, axisLabel: { formatter: displayNumber } },
            dataZoom: [{ type: 'inside', filterMode: 'none' }], series });
          observer = new ResizeObserver(() => chart.resize()); observer.observe(element.current);
        }).catch(e => !disposed && setError(e.message));
        return () => { disposed = true; observer?.disconnect(); chart?.dispose(); };
      }, [plot]);
      return h('div', null, error && h('p', { className: 'hz-error', role: 'alert' }, error), h('div', { ref: element, className: 'hz-scientific-chart', role: 'img', 'aria-label': t(plot.id) + ': ' + plot.x_label + ' / ' + plot.y_label }));
    }
    function StructureView({ value, t, volume }) {
      const element = useRef(null), viewerRef = useRef(null), defaultView = useRef(null), [hidden, setHidden] = useState([]), [cell, setCell] = useState(true), [repeats, setRepeats] = useState(1), [error, setError] = useState('');
      const elements = [...new Set(value.symbols)];
      const showCell = viewer => {
        viewer.removeAllShapes();
        if (volume?.level > 0) {
          const density = new window.$3Dmol.VolumeData(volume.cube, 'cube');
          viewer.addIsosurface(density, { isoval: volume.level, color: '#D96B43', alpha: .65, smoothness: 1 });
          viewer.addIsosurface(density, { isoval: -volume.level, color: '#3C5488', alpha: .65, smoothness: 1 });
        }
        if (!cell || !value.cell_angstrom) return;
        const corners = Array.from({ length: 8 }, (_, i) => value.cell_angstrom.reduce((v, a, axis) => v.map((n, j) => n + ((i >> axis) & 1)*a[j]*repeats), [0, 0, 0]));
        corners.forEach((start, i) => { for (let axis = 0; axis < 3; axis++) if (!((i >> axis) & 1)) { const end = corners[i | (1 << axis)]; viewer.addLine({ start: { x: start[0], y: start[1], z: start[2] }, end: { x: end[0], y: end[1], z: end[2] }, color: '#6b87a9', linewidth: 1 }); } });
      };
      useEffect(() => {
        if (value.coordinate_dimension === 2) return;
        let disposed = false, viewer, observer;
        loadVisualLibrary('molecule', '$3Dmol').then(library => {
          if (disposed) return;
          viewer = library.createViewer(element.current, { backgroundColor: '#ffffff', antialias: true }); viewerRef.current = viewer;
          const sites = [];
          for (let a = 0; a < repeats; a++) for (let b = 0; b < repeats; b++) for (let c = 0; c < repeats; c++) {
            const offset = value.cell_angstrom ? value.cell_angstrom.reduce((p, v, axis) => p.map((n, j) => n + [a,b,c][axis]*v[j]), [0,0,0]) : [0,0,0];
            value.symbols.forEach((symbol, i) => sites.push(symbol + ' ' + value.positions_angstrom[i].map((v, j) => v + offset[j]).join(' ')));
          }
          const xyz = sites.length + '\nSupplied coordinates\n' + sites.join('\n');
          viewer.addModel(xyz, 'xyz');
          viewer.setStyle({}, { sphere: { scale: .28 }, stick: { radius: .1 } });
          showCell(viewer);
          viewer.zoomTo(); viewer.zoom(1.5); viewer.rotate(25, 'x'); viewer.rotate(-20, 'y'); defaultView.current = viewer.getView(); viewer.render(); observer = new ResizeObserver(() => { viewer.resize(); viewer.render(); }); observer.observe(element.current);
        }).catch(e => !disposed && setError(e.message));
        return () => { disposed = true; observer?.disconnect(); viewer?.clear(); viewerRef.current = null; if (element.current) element.current.replaceChildren(); };
      }, [value, repeats, volume]);
      useEffect(() => {
        const viewer = viewerRef.current; if (!viewer) return;
        viewer.setStyle({}, { sphere: { scale: .28 }, stick: { radius: .1 } });
        hidden.forEach(elem => viewer.setStyle({ elem }, {}));
        showCell(viewer); viewer.render();
      }, [hidden, cell]);
      return h('section', { className: 'hz-structure-view' }, value.label && h('strong', null, t(value.label)),
        value.coordinate_dimension === 2 ? h('img', { className: 'hz-molecule-2d', src: 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(value.depiction), alt: t('dimension2') }) : h('div', { ref: element, className: 'hz-structure-canvas', role: 'img', 'aria-label': t('structureViewer') }),
        error && h('p', { className: 'hz-error', role: 'alert' }, error),
        h('div', { className: 'hz-view-toolbar' }, note(value.cell_angstrom ? t('cellAtoms') + ': ' + value.atom_count + (repeats > 1 ? ' · ' + t('displayedAtoms') + ': ' + value.atom_count * repeats**3 : '') : value.atom_count + ' ' + t('atoms')),
          value.coordinate_dimension !== 2 && button(t('resetView'), () => { if (defaultView.current) viewerRef.current?.setView(defaultView.current); viewerRef.current?.render(); }),
          value.cell_angstrom && h('label', null, h('input', { type: 'checkbox', checked: cell, onChange: e => setCell(e.target.checked) }), t('unitCell')),
          value.cell_angstrom && !volume && value.symbols.length * 8 <= 20000 && h('select', { value: repeats, 'aria-label': t('unitCell'), onChange: e => setRepeats(Number(e.target.value)) }, option(1, '1 × 1 × 1'), option(2, '2 × 2 × 2')),
          volume && note(t('densityIsosurface') + ': ±' + displayNumber(volume.level) + ' ' + volume.unit + ' · ' + t('densityColors')),
          ...elements.map(elem => h('label', { key: elem }, h('input', { type: 'checkbox', checked: !hidden.includes(elem), onChange: e => setHidden(e.target.checked ? hidden.filter(v => v !== elem) : [...hidden, elem]) }), elem))));
    }
    function NativeStructurePreview({ content, resourceAddress, t }) {
      const [value, setValue] = useState(null), [error, setError] = useState('');
      useEffect(() => {
        if (content.kind !== 'bytes') return;
        let active = true; setValue(null); setError('');
        if (!/\.(mol|sdf)$/i.test(resourceAddress)) loadVisualLibrary('molecule', '$3Dmol').catch(() => {});
        api('structure.visual', { text: new TextDecoder().decode(content.data), name: decodeURIComponent(resourceAddress.split('/').pop()) }).then(v => active && setValue(v)).catch(e => active && setError(e.message));
        return () => { active = false; };
      }, [content, resourceAddress]);
      return h('div', { className: 'hz-native-structure' }, error ? h('p', { className: 'hz-error', role: 'alert' }, error) : value ? h(StructureView, { value, t }) : note(t('loading')));
    }
    for (const labels of [zh, en]) Object.assign(labels, { km: 'Kₘ', Km: 'Kₘ', vmax: 'Vₘₐₓ', Vmax: 'Vₘₐₓ', km_se: 'SE(Kₘ)', vmax_se: 'SE(Vₘₐₓ)' });
    function ResultTable({ table, t, openFile, selectRow, selected, paginate = true, filterable = true }) {
      const [page, setPage] = useState(0), [query, setQuery] = useState('');
      const rows = table.rows.filter(row => !query || JSON.stringify(row).toLowerCase().includes(query.toLowerCase()));
      const size = paginate ? 20 : Math.max(1, rows.length);
      const keys = table.columns || Object.keys(table.rows[0] || {}), pages = Math.max(1, Math.ceil(rows.length / size)), current = Math.min(page, pages - 1);
      function cell(value, key) {
        if (key === 'sources') return value.map((ref, i) => h('div', { key: i }, button(ref.file.split('/').pop() + ' · ' + ref.locator, () => openFile(ref.file))));
        if (key === 'file') return value.split(/[\\/]/).pop();
        if (typeof value === 'boolean' || (typeof value === 'string' && /^(True|False|true|false)$/.test(value))) return h('span', { className: 'hz-value-state', 'data-state': String(value).toLowerCase() }, t(String(value).toLowerCase() === 'true' ? 'yes' : 'no'));
        if (['state', 'review', 'validationOutcome'].includes(key)) return h('span', { className: 'hz-value-state', 'data-state': value }, t(value));
        if (['role', 'field', 'energy_reference'].includes(key)) return t(value);
        if (Array.isArray(value)) return value.map(displayNumber).join(key === 'window_eV' ? ' … ' : ' · ');
        if (typeof value === 'object' && value !== null) return Object.entries(value).map(([k, v]) => t(k) + ': ' + displayNumber(v)).join(' · ');
        return displayNumber(value);
      }
      return h('section', { className: 'hz-result-table' }, h('div', { className: 'hz-view-toolbar' }, h('strong', null, t(table.id)), filterable && input(query, value => { setQuery(value); setPage(0); }, { placeholder: t('filterRows'), 'aria-label': t('filterRows') })),
        h('div', { className: 'hz-table-scroll' }, h('table', null, h('thead', null, h('tr', null, ...keys.map(key => h('th', { key, scope: 'col' }, t(key))))),
          h('tbody', null, ...rows.slice(current*size, (current+1)*size).map((row, index) => h('tr', { key: current*size+index, className: selected === row ? 'hz-selected-row' : '', onClick: selectRow ? () => selectRow(row) : undefined, tabIndex: selectRow ? 0 : undefined, onKeyDown: selectRow ? event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectRow(row); } } : undefined }, ...keys.map(key => h('td', { key, title: typeof row[key] === 'object' ? undefined : String(row[key] ?? '') }, cell(row[key], key)))))))),
        paginate && h('div', { className: 'hz-view-toolbar hz-pagination' }, note(rows.length + ' · ' + (current+1) + ' / ' + pages), button(t('previous'), () => setPage(current-1), current === 0), button(t('next'), () => setPage(current+1), current+1 >= pages)));
    }
    function ArtifactImage({ image, request, selected, t }) {
      const [url, setUrl] = useState(''), [error, setError] = useState('');
      useEffect(() => { let active = true; api('artifact.media', { ...request, file: image.file }).then(v => active && setUrl(v.url)).catch(e => active && setError(e.message)); return () => { active = false; }; }, [image.file, request.caseId, request.artifactId]);
      const bounds = selected && ['left', 'top', 'right', 'bottom'].every(k => selected[k] !== undefined) ? selected : null;
      return h('figure', { className: 'hz-result-image' }, error && h('p', { className: 'hz-error' }, error), url ? h('div', { className: 'hz-image-frame' }, h('img', { src: url, alt: image.label }), bounds && h('svg', { viewBox: '0 0 1 1', preserveAspectRatio: 'none', 'aria-hidden': true }, h('rect', { x: bounds.left, y: bounds.top, width: bounds.right-bounds.left, height: bounds.bottom-bounds.top, fill: 'none', stroke: '#0052cc', strokeWidth: .006 }))) : note(t('loading')));
    }
    function ArtifactOverview({ request, reportFile, title, close, openFile, t }) {
      const storedView = panelPreferences(request.projectId).preview;
      const priorView = storedView?.artifactId === request.artifactId && storedView?.revision === request.revision ? storedView : null;
      const [view, setView] = useState(null), [error, setError] = useState(''), [plotId, setPlotId] = useState(''), [imageIndex, setImageIndex] = useState(priorView?.imageIndex || 0), [structureIndex, setStructureIndex] = useState(priorView?.structureIndex || '0'), [selected, setSelected] = useState(null);
      useEffect(() => { let active = true; api('artifact.visual', request).then(v => { if (active) { setView(v); setPlotId(v.charts.some(p => p.id === priorView?.plotId) ? priorView.plotId : v.charts.find(p => p.id === 'scf-accuracy_Ry')?.id || v.charts[0]?.id || ''); } }).catch(e => active && setError(e.message)); return () => { active = false; }; }, [request.artifactId, request.caseId, request.revision]);
      useEffect(() => { if (view) savePanelPreferences(request.projectId, { preview: { artifactId: request.artifactId, revision: request.revision, plotId, imageIndex, structureIndex } }); }, [view, plotId, imageIndex, structureIndex]);
      const groups = {};
      for (const file of view?.artifact.relatedFiles || []) {
        const role = Object.entries(view.artifact.files || {}).find(([, value]) => value === file)?.[0] || '';
        const group = /structure|input|pseudopotential/.test(role) ? 'inputs' : /qe_out|log|stdout|stderr/.test(role) ? 'rawOutput' : /\.(png|svg|jpe?g|webp)$/i.test(file) ? 'images' : /\.(csv|tsv|xlsx)$/i.test(file) ? 'tables' : /\.(py|js|sh|ps1)$/i.test(file) ? 'scripts' : /\.(md|pdf|docx)$/i.test(file) ? 'documents' : /\.json$/i.test(file) ? 'configuration' : 'otherFiles';
        (groups[group] ||= []).push(file);
      }
      const plot = view?.charts.find(p => p.id === plotId);
      return h(Modal, { open: true, onClose: close, closeLabel: t('close'), title: view?.artifact.title || title, className: 'hz-result-dialog', contentClassName: 'hz-result-dialog-content' },
        h('div', { className: 'hz-result-overview' }, h('div', { className: 'hz-view-toolbar' }, button(t('report'), () => openFile(reportFile))), error && h('p', { className: 'hz-error', role: 'alert' }, error), !view && !error && note(t('loading')),
          view && h(React.Fragment, null,
            view.metrics.length > 0 && h('div', { className: 'hz-metrics' }, ...view.metrics.map((metric, i) => h('div', { key: i }, h('span', null, t(metric.label)), h('strong', { title: String(metric.value ?? '') }, typeof metric.value === 'boolean' ? t(metric.value ? 'yes' : 'no') : metric.label === 'Energy' ? String(metric.value ?? '—') : t(displayNumber(metric.value))), metric.se !== null && metric.se !== undefined && h('small', null, 'SE ' + displayNumber(metric.se)), metric.unit && h('small', null, metric.unit)))),
            view.depiction && h('img', { className: 'hz-molecule-2d', src: 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(view.depiction), alt: t('structureViewer') }),
            view.reactions?.length > 0 && h('div', { className: 'hz-reaction-equations' }, ...view.reactions.map((reaction, i) => h('div', { key: i }, h('strong', null, reaction.equation), h('span', null, 'k = ' + displayNumber(reaction.k) + ' ' + reaction.unit), h('span', null, t(reaction.basis))))),
            h('div', { className: 'hz-result-visuals', 'data-layout': view.structures.length && plot ? 'paired' : 'single' },
              view.structures.length > 0 && h('div', { className: 'hz-structure-group' }, view.structures.length > 1 && h(SegmentedTabs, { value: structureIndex, onChange: setStructureIndex, label: t('structures'), items: view.structures.map((value, i) => ({ value: String(i), label: t(value.label || 'structures') })) }), h(StructureView, { key: structureIndex, value: view.structures[Number(structureIndex)], volume: view.volume?.model_label === view.structures[Number(structureIndex)].label ? view.volume : null, t })),
              plot && h('section', { className: 'hz-chart-group' }, view.charts.length > 1 && h(SegmentedTabs, { value: plotId, onChange: setPlotId, label: t('figures'), items: view.charts.map(p => ({ value: p.id, label: t(p.id) })) }), view.figure_file && plotId === 'fit' ? h(ArtifactImage, { image: { file: view.figure_file, label: t('fit') }, request, t }) : h(ScientificChart, { plot, t }))),
            view.images.length > 0 && h('section', null, view.images.length > 1 && h('div', { className: 'hz-view-toolbar' }, h('select', { value: imageIndex, 'aria-label': t('image'), onChange: e => { setImageIndex(Number(e.target.value)); setSelected(null); } }, ...view.images.map((image, i) => option(i, image.label)))), h(ArtifactImage, { image: view.images[imageIndex], request, selected, t })),
            view.kind === 'colorimetry' && selected && h('div', { className: 'hz-color-sample' }, h('span', { style: { background: 'rgb(' + [selected.mean_r, selected.mean_g, selected.mean_b].join(',') + ')' } }), h('div', null, t('rgb') + ': ' + [selected.mean_r, selected.mean_g, selected.mean_b].map(v => displayNumber(Number(v))).join(' / '), h('br'), t('hsv') + ': ' + [selected.mean_h, selected.mean_s, selected.mean_v].map(v => displayNumber(Number(v))).join(' / '))),
            ...view.tables.map(table => h(ResultTable, { key: table.id, table, t, openFile, selected, selectRow: view.kind === 'colorimetry' ? row => { setSelected(row); const index = view.image_records.findIndex(image => image.file === row.file); if (index >= 0) setImageIndex(index); } : null })),
            view.conditions && h('details', null, h('summary', null, t('conditions')), h('pre', null, typeof view.conditions === 'string' ? view.conditions : JSON.stringify(view.conditions, null, 2))),
            view.parameters && h('details', null, h('summary', null, t('parameters')), h('pre', null, JSON.stringify(view.parameters, null, 2))),
            ...(view.warnings || []).map((warning, i) => note(warning)),
            h('details', null, h('summary', null, t('sourceFiles')), ...Object.entries(groups).map(([role, files]) => h('section', { key: role, className: 'hz-file-role' }, h('strong', null, t(role)), ...files.map(file => button(file.split('/').pop(), () => openFile(file)))))),
            h('div', { className: 'hz-view-toolbar hz-result-footer' }, note(t(request.caseId ? 'pinnedVersion' : 'savedVersion') + ' · ' + view.artifact.revision.slice(0, 8)), null))));
    }
    function Actions({ label, items, onSelect }) {
      const [open, setOpen] = useState(false);
      return h(Menu, { open, items: items.map(item => item.id === 'trash' ? { ...item, icon: h(IconTrashOutlineRegular, {}) } : item), portal: true, align: 'end', onClose: () => setOpen(false), onSelect: id => { setOpen(false); onSelect(id); }, anchor: h(Button, { size: 'sm', variant: 'ghost', 'aria-label': label, title: label, 'aria-haspopup': 'menu', 'aria-expanded': open, onClick: () => setOpen(!open) }, '⋯') });
    }
    function Notices({ d }) { return h(React.Fragment, null, d.error && h('p', { className: 'hz-error', role: 'alert' }, d.error), d.notice && h('p', { className: 'hz-success', role: 'status' }, d.notice)); }
    async function openFiles(id, file) {
      let sessionId = catalog.projects.find(p => p.id === id)?.sessions.includes(currentSession) ? currentSession : await context.uiWorkspace.connectWorkspace(id);
      context.uiWorkspace.openSession(sessionId);
      const deadline = performance.now() + 5000;
      while (performance.now() < deadline) {
        await new Promise(requestAnimationFrame);
        if (context.sidebarRight.mounted.getSnapshot() !== sessionId) continue;
        if (file) context.sidebarRight.openResource('dsh-resource://file/session/' + sessionId + '/' + file.split('/').map(encodeURIComponent).join('/'));
        else context.sidebarRight.openTab('files');
        return;
      }
      throw new Error('Project view is still loading. Try again.');
    }
    async function launchResources(sessionId, tab, request = null) {
      currentSession = sessionId; draftRequest = request;
      const next = await api('state'); publishCatalog(next);
      const p = next.projects.find(p => p.sessions.includes(sessionId));
      if (!p) return;
      const selected = tab || panelPreferences(p.id).tab || 'files';
      savePanelPreferences(p.id, { tab: selected });
      await openFiles(p.id); window.dispatchEvent(new CustomEvent('highzyme:navigate', { detail: { projectId: p.id, tab: selected } })); changed();
    }
    function CaseList({ d, t }) {
      const [editing, setEditing] = useState(''), [renamed, setRenamed] = useState('');
      const cases = d.detail.cases.filter(c => c.status === 'active');
      const start = c => d.act(async () => {
        const sessionId = await context.sessions.create({ workspaceId: d.id, agentPreset: 'research' });
        await api('case.attach', { projectId: d.id, caseId: c.id, sessionId });
        await context.sessions.refresh(); context.uiWorkspace.openSession(sessionId);
      });
      const update = (c, status) => d.act('case.update', { caseId: c.id, status }, t('success')).then(async () => {
        await context.sessions.refresh(); changed();
      });
      return h(React.Fragment, null,
        h('div', { className: 'hz-toolbar' }, button(t('newCase'), () => window.dispatchEvent(new CustomEvent('highzyme:new', { detail: { projectId: d.id, kind: 'cases' } })), d.busy, true)),
        !cases.length && note(t('noCases')),
        ...cases.map(c => h('article', { className: 'hz-record', key: c.id },
          h('div', { className: 'hz-record-main' }, h('strong', null, c.title), c.references.length > 0 && h('details', null, h('summary', null, t('references') + ' · ' + c.references.length), ...c.references.map(r => h('div', { className: 'hz-reference', key: r.artifactId }, r.title, h('code', null, r.revision.slice(0, 8)))))),
          h('div', { className: 'hz-actions' }, c.status === 'active' ? button(t(c.sessions.length ? 'continue' : 'start'), () => c.sessions.length ? context.uiWorkspace.openSession(c.sessions.at(-1)) : start(c), d.busy) : button(t('restore'), () => update(c, 'active'), d.busy),
            h(Actions, { label: t('caseMenu'), items: [{ id: 'rename', label: t('rename') }, ...(c.status === 'active' ? [{ id: 'archived', label: t('archive') }] : []), ...(c.status !== 'trash' ? [{ id: 'trash', label: t('trash'), danger: true }] : [])], onSelect: id => { if (id === 'rename') { setEditing(c.id); setRenamed(c.title); } else update(c, id); } })),
          editing === c.id && h('form', { className: 'hz-inline-form', onSubmit: async e => { e.preventDefault(); if (await d.act('case.update', { caseId: c.id, title: renamed })) setEditing(''); } }, input(renamed, setRenamed, { 'aria-label': t('rename'), autoFocus: true }), h(Button, { type: 'submit', variant: 'outline', size: 'sm', disabled: d.busy }, t('save')), button(t('cancel'), () => setEditing(''))))));
    }
    function Artifacts({ d, t }) {
      const [form, setForm] = useState(null), [mode, setMode] = useState('new'), [range, setRange] = useState(null), [picked, setPicked] = useState([]), [all, setAll] = useState(true), [rounds, setRounds] = useState(1), [job, setJob] = useState(null), [destination, setDestination] = useState(''), [expanded, setExpanded] = useState(false);
      const sessions = useSyncExternalStore(context.sessions.list.subscribe, context.sessions.list.getSnapshot);
      const sourceName = id => d.detail.cases.find(c => c.sessions.includes(id))?.title || sessions.byId[id]?.displayTitle || id;
      const openRange = async (sessionId, locked = false, ids) => {
        const result = await d.act('conversation.messages', { sessionId });
        if (result) { setRange({ sessionId, turns: result.turns, locked }); setPicked(ids || []); setAll(!ids); setRounds(1); setExpanded(true); }
      };
      const loadDraft = async id => {
        const result = await d.act('artifact.draft', { jobId: id });
        if (!result) return;
        if (result.status === 'completed') { const { title, fileStem, content, kind, sessionId, caseId, sourceMessageIds, sourceReferences } = result; setForm({ title, fileStem, content, kind, sessionId, caseId, sourceMessageIds, sourceReferences, draftJobId: id }); setJob(null); setRange(null); setMode('new'); }
        else if (result.status !== 'running') { setJob(null); throw new Error(result.detail || t(result.status)); }
        else setJob(result);
      };
      useEffect(() => { const consume = () => {
        const request = draftRequest; if (!request) return; draftRequest = null; setExpanded(true);
        if (request.jobId) { d.act(() => loadDraft(request.jobId)); return; }
        if ((form?.sessionId || job?.sessionId) === request.sessionId && !request.messageId && !request.retryMessageIds) return;
        setForm(null); setJob(null);
        if (request.messageId) d.act('conversation.document', request).then(result => { if (result) { setForm(result); setRange(null); setMode('new'); } });
        else openRange(request.sessionId, !request.retryMessageIds, request.retryMessageIds);
      }; consume(); window.addEventListener('highzyme:navigate', consume); return () => window.removeEventListener('highzyme:navigate', consume); }, [d.id, d.sessionId, !!form, form?.sessionId, job?.id]);
      useEffect(() => { if (!job) return; const timer = setInterval(() => { d.act(() => loadDraft(job.id)); }, 1800); return () => clearInterval(timer); }, [job?.id]);
      useEffect(() => { if (!form || mode === 'existing') return; let active = true; api('artifact.path', { projectId: d.id, sessionId: d.sessionId, file: form.file, fileStem: form.fileStem, title: form.title, kind: form.kind, caseId: form.caseId, ...(form.sessionId ? {sessionId: form.sessionId} : {}) }).then(value => { if (active) setDestination(value.file); }).catch(() => { if (active) setDestination(''); }); return () => { active = false; }; }, [d.id, form?.file, form?.fileStem, form?.title, form?.sessionId, mode]);
      const edit = (key, value) => setForm(old => ({ ...old, [key]: value }));
      const selectedRounds = range?.turns.filter(turn => turn.messages.some(m => picked.includes(m.id))).length || 0;
      const selectMessages = (ids, checked) => setPicked(old => checked ? [...new Set([...old, ...ids])] : old.filter(id => !ids.includes(id)));
      const pendingDrafts = d.detail.jobs.filter(j => j.type === 'organize' && !j.savedArtifactId && ['completed', 'running'].includes(j.status) && j.id !== job?.id && j.id !== form?.draftJobId);
      return h(React.Fragment, null,
        h('div', { className: 'hz-toolbar' }, button(t('fromConversation'), () => form || job ? setExpanded(true) : openRange(d.sessionId), d.busy), button(t('addArtifact'), () => { setForm({ title: '', content: '', kind: 'source', file: '', sessionId: d.sessionId }); setRange(null); setMode('new'); setExpanded(true); }, d.busy || !!job)),
        (range || job || form) && h('section', { className: 'hz-organizer' },
          h('button', { type: 'button', className: 'hz-fold-heading', 'aria-expanded': expanded, onClick: () => setExpanded(!expanded) }, h('span', { 'aria-hidden': true }, expanded ? '▾' : '▸'), h('span', null, job ? t('organizing') : form ? t('pendingDraft') : t('fromConversation')), h('small', null, sourceName(form?.sessionId || job?.sessionId || range?.sessionId || d.sessionId))),
          h('div', { hidden: !expanded },
        range && !job && !form && h('section', { className: 'hz-artifact-form' },
          !range.locked && field(t('sourceSession'), h('select', { value: range.sessionId, disabled: d.busy, onChange: e => openRange(e.target.value) }, ...d.project.sessions.map(id => option(id, sourceName(id))))),
          !range.locked && field(t('chooseMessages'), h('select', { value: all ? 'all' : 'picked', onChange: e => setAll(e.target.value === 'all') }, option('all', t('allMessages')), option('picked', t('selectedMessages')))),
          all ? field(t('rounds'), input(rounds, v => setRounds(v === '' ? '' : Number(v)), { type: 'number', min: 1, max: 15, step: 1, disabled: d.busy })) : h(React.Fragment, null,
            note(t('selectedMessages') + ' · ' + selectedRounds + '/15'),
            h('div', { className: 'hz-message-picker' }, ...range.turns.map(turn => {
              const selected = turn.messages.some(m => picked.includes(m.id)), capped = selectedRounds >= 15 && !selected;
              return h('div', { key: turn.index, className: 'hz-message-round' },
                h('label', { className: 'hz-round-check' }, h('input', { type: 'checkbox', checked: turn.messages.every(m => picked.includes(m.id)), disabled: capped, 'aria-label': t('selectRound') + ' ' + turn.index, onChange: e => selectMessages(turn.messages.map(m => m.id), e.target.checked) }), t('round') + ' ' + turn.index),
                ...turn.messages.map(m => h('label', { key: m.id, className: 'hz-message-choice' }, h('input', { type: 'checkbox', checked: picked.includes(m.id), disabled: capped, onChange: e => selectMessages([m.id], e.target.checked) }), h('span', null, h('small', null, t(m.role)), h('span', { className: 'hz-message-excerpt' }, m.preview)))));
            }))),
          h('div', { className: 'hz-actions' }, button(t('organize'), () => d.act('artifact.organize', { sessionId: range.sessionId, currentSessionId: d.sessionId, ...(all ? { rounds } : { messageIds: picked }), language: t('save') === 'Save' ? 'en' : 'zh' }).then(value => { if (value) { setJob(value); setRange(null); } }), d.busy || (all ? !Number.isInteger(rounds) || rounds < 1 || rounds > 15 : !picked.length), true), button(t('collapse'), () => setExpanded(false)))),
        job && h('div', { className: 'hz-toolbar', role: 'status' }, t('organizing'), button(t('stop'), () => d.act('task.cancel', { jobId: job.id }).then(() => setJob(null)), d.busy)),
        form && h('form', { className: 'hz-artifact-form', onSubmit: async e => { e.preventDefault(); const values = { ...form, currentSessionId: d.sessionId }; if (mode === 'existing') delete values.content; if (!values.file) delete values.file; if (await d.act('artifact.save', values, t('registered'))) { setForm(null); setRange(null); setExpanded(false); } } },
          field(t('title'), input(form.title, v => edit('title', v), { required: true })),
          !form.id && h('div', { className: 'hz-tabs' }, ...['new', 'existing'].map(v => h('button', { key: v, type: 'button', className: mode === v ? 'is-active' : '', onClick: () => setMode(v) }, t(v === 'new' ? 'newDocument' : 'existingFile')))),
          mode === 'existing' ? field(t('file'), input(form.file || '', v => edit('file', v), { required: true })) : field(t('body'), h('textarea', { value: form.content, onChange: e => edit('content', e.target.value), rows: 12, required: true })),
          h('details', { className: 'hz-artifact-options' }, h('summary', null, t('kind') + ' / ' + t('destination')), field(t('kind'), h('select', { value: form.kind, onChange: e => edit('kind', e.target.value) }, ...(mode === 'existing' || form.id ? ['source', 'plan', 'result', 'code', 'data'] : ['source', 'plan', 'result']).map(v => option(v, t(v))))), !form.file && mode !== 'existing' && field(t('fileStem'), input(form.fileStem || '', v => edit('fileStem', v), { pattern: '[a-z0-9]+(-[a-z0-9]+)*', placeholder: 'research-note' })), note(mode === 'existing' ? form.file : destination), (mode === 'existing' || form.id) && field(t('relatedFiles'), h('textarea', { value: (form.relatedFiles || []).filter(file => file !== form.file).join('\n'), rows: 3, onChange: e => edit('relatedFiles', e.target.value.split('\n').map(file => file.trim()).filter(Boolean)) }))),
          h('div', { className: 'hz-actions' }, h(Button, { type: 'submit', variant: 'primary', size: 'sm', disabled: d.busy }, t('save')), button(t('collapse'), () => setExpanded(false)))),
          )),
        ...pendingDrafts.map(j => h('div', { key: j.id, className: 'hz-pending-draft' }, h('span', null, (j.status === 'running' ? t('organizing') : t('pendingDraft')) + ' · ' + (j.title || sourceName(j.sessionId))), button(t('draft'), () => { setExpanded(true); d.act(() => loadDraft(j.id)); }, d.busy))),
        !d.detail.artifacts.length && !form && note(t('noArtifacts')),
        ...d.detail.artifacts.map(a => h(ArtifactRecord, { key: a.id, artifact: a, d, t, edit: content => { setForm({ ...a, content }); setRange(null); setMode('new'); setExpanded(true); } })));
    }
    function ArtifactRecord({ artifact: a, d, t, edit }) {
      const currentCase = d.detail.cases.find(c => c.sessions.includes(d.sessionId));
      const reference = currentCase?.references.find(r => r.artifactId === a.id);
      const [snapshot, setSnapshot] = useState(null);
      const [showOverview, setShowOverview] = useState(false);
      useEffect(() => { setSnapshot(null); }, [reference?.revision]);
      const visible = snapshot || reference || a;
      const members = visible.relatedFiles || [visible.file];
      const preview = file => d.act(async () => {
        if (!reference) return openFiles(d.id, file);
        const saved = await api('artifact.file', { projectId: d.id, sessionId: d.sessionId, artifactId: a.id, caseId: currentCase.id, file });
        await openFiles(d.id, saved.file);
      }, { refresh: false });
      const prepare = kind => d.act(async () => {
        const binding = context.sessions.binding(d.sessionId);
        const value = context.get('conversation')?.input.requestDraftInitialization(binding, { prompt: t(kind + 'Prompt') + '\n' + a.title + '\n' + a.file });
        if (value !== 'applied') throw new Error(t('draftOccupied'));
      }, { refresh: false }, t('taskPrepared'));
      const request = { projectId: d.id, sessionId: d.sessionId, artifactId: a.id, revision: visible.revision, ...(reference ? { caseId: currentCase.id } : {}) };
      const rich = members.some(file => /\.(png|svg|jpe?g|webp|cif|mmcif|pdb|mol|sdf|xyz|extxyz|vasp)$/i.test(file) || /(?:result|evidence|comparison)\.json$/i.test(file));
      return h('article', { className: 'hz-record', onPointerEnter: () => rich && warmVisualLibraries({ ...visible, analysis: a.analysis }), onFocus: () => rich && warmVisualLibraries({ ...visible, analysis: a.analysis }) }, showOverview && h(ArtifactOverview, { request, reportFile: visible.mainFile || visible.file, title: visible.title, close: () => setShowOverview(false), openFile: file => { setShowOverview(false); return reference && !members.includes(file) ? openFiles(d.id, file) : preview(file); }, t }), h('div', { className: 'hz-record-main' }, h('strong', null, visible.title), note(t(a.kind)),
        h('details', { onToggle: event => { if (event.currentTarget.open && reference && !reference.relatedFiles && !snapshot) d.act('artifact.read', { artifactId: a.id, caseId: currentCase.id, metadataOnly: true }).then(value => value && setSnapshot(value)); } }, h('summary', null, t('relatedFiles') + ' · ' + members.length),
          ...members.map(file => h('div', { key: file }, button(file.split('/').pop(), () => preview(file), d.busy)))),
        h('details', null, h('summary', null, t('sourceSession')), a.sessionId ? d.project.sessions.includes(a.sessionId) ? button(context.sessions.list.getSnapshot().byId[a.sessionId]?.displayTitle || d.detail.sessionTitles[a.sessionId] || a.sessionId, () => context.uiWorkspace.openSession(a.sessionId)) : t('sourceDeleted') : '—', note(t(reference ? 'pinnedVersion' : 'savedVersion') + ' · ' + (visible.revision?.slice(0, 8) || '—')))),
        h('div', { className: 'hz-actions' }, button(t('overview'), () => { if (rich) { warmVisualLibraries({ ...visible, analysis: a.analysis }); setShowOverview(true); } else preview(visible.file); }, d.busy),
          h(Actions, { label: t('artifactMenu'), items: [
            ...(reference ? [{ id: 'current', label: t('currentArtifact') }, { id: 'update-reference', label: t('updateReference') }] : []),
            ...(/^(fit_kinetics|calculation|save_evidence|compare_evidence):/.test(a.analysis?.operation || '') ? [{ id: 'reviseAnalysis', label: t('reviseAnalysis') }, { id: 'newAnalysis', label: t('newAnalysis') }] : []),
            ...(/\.(md|txt|csv|tsv|json|ya?ml|py|js|ts|html|css|xml|tex|sh|ps1)$/i.test(a.file) ? [{ id: 'edit', label: t('edit') }] : []),
            { id: 'reference', label: t('useVersion'), disabled: !d.detail.cases.some(c => c.status === 'active'), submenu: d.detail.cases.filter(c => c.status === 'active').map(c => ({ id: c.id, label: c.title })) }], onSelect: id => {
            if (id === 'current') d.act(() => openFiles(d.id, a.file), { refresh: false });
            else if (id === 'edit') d.act('artifact.read', { artifactId: a.id }).then(value => value && edit(value.content));
            else if (id === 'reviseAnalysis' || id === 'newAnalysis') prepare(id);
            else d.act('artifact.reference', { artifactId: a.id, caseId: id === 'update-reference' ? currentCase.id : id }, t('cited'));
          } })));
    }
    function ComputeTaskDetail({ job: j, d, t }) {
      const resource = d.state.resources.find(r => r.id === j.resource_id), request = j.qe?.request, specs = j.resources;
      return h('div', { className: 'hz-compute-task' },
        note(t('executionLocation') + ': ' + (j.type === 'compute' ? resource?.name || j.resource_id : t('localExecution'))),
        j.scheduler_id && note('Slurm · ' + j.scheduler_id), j.elapsed && note(t('elapsed') + ': ' + j.elapsed),
        j.status === 'queued' && j.reason && note(t('queueReason') + ': ' + j.reason),
        j.progress && note(t('calculationStages') + ': ' + j.progress.stages.filter(s => s.status === 'completed').length + ' / ' + (j.qe?.stages?.length || j.progress.stages.length) + (j.progress.stages.at(-1)?.id ? ' · ' + j.progress.stages.at(-1).id : '')),
        j.validation && h('details', null, h('summary', null, j.validation.candidate_title + ' · ' + j.validation.candidate_revision.slice(0, 8)), h('p', null, j.validation.question), h('p', null, t('validationCriterion') + ': ' + j.validation.criterion)),
        j.qe?.workflow && h('details', { className: 'hz-prepared-summary' }, h('summary', null, t(j.qe.method)), ...j.qe.stages.map(stage => note(stage.id + ' · ' + stage.program)),
          j.qe.summary && h('details', null, h('summary', null, t('parameters')), h('pre', null, JSON.stringify(j.qe.summary, null, 2))),
          button(t('inspectInput'), () => openFiles(d.id, j.qe.folder + '/workflow.json'))),
        specs && note(specs.ranks + ' MPI × ' + specs.threads + ' ' + t('threads') + ' · ' + specs.memory_mb + ' MiB · ' + specs.timeout_seconds + ' s'),
        request && h('div', { className: 'hz-prepared-summary' },
          h('strong', null, request.structure.formula + ' · ' + request.structure.atoms + ' ' + t('atoms') + ' · ' + request.parameters.calculation.toUpperCase()),
          note('ecutwfc: ' + request.parameters.ecutwfc + ' Ry · ecutrho: ' + request.parameters.ecutrho + ' Ry · k: ' + request.parameters.kpoints.join(' × ')),
          h('details', null, h('summary', null, t('parameters')), h('pre', null, JSON.stringify(request.parameters, null, 2))),
          h('div', { className: 'hz-actions' }, ...(j.qe.inputs || []).map(f => button(f.file.split('/').pop(), () => openFiles(d.id, f.file))))),
        j.status === 'submission_unknown' && note(t('submissionHelp')),
        (j.last_error || j.error) && note(j.last_error || j.error),
        ['failed', 'timed_out', 'cancelled'].includes(j.status) && j.scheduler_state && note(t('failureReason') + ': ' + j.scheduler_state + (j.exit_code ? ' · ' + j.exit_code : '')),
        j.stderr && h('details', null, h('summary', null, t('rawOutput')), h('pre', null, j.stderr)));
    }
    function Tasks({ d, t, active: visible = true }) {
      const activeStates = ['pending', 'prepared', 'submitting', 'submission_unknown', 'queued', 'running', 'waiting', 'blocked'];
      const importing = j => j.qe && !j.artifactId && ['completed', 'failed', 'timed_out', 'cancelled'].includes(j.status) && !['failed', 'skipped'].includes(j.collection_status);
      const active = d.detail.jobs.filter(j => activeStates.includes(j.status) || importing(j));
      const notices = d.detail.jobs.filter(j => (['failed', 'interrupted'].includes(j.status) && !importing(j) || j.collection_status === 'failed') && !j.acknowledged);
      useEffect(() => { if (!visible || !active.length) return; const timer = setInterval(() => { if (!document.hidden) d.refresh({ jobsOnly: true }); }, 3000); return () => clearInterval(timer); }, [visible, active.length > 0, d.refresh]);
      return h('div', { className: 'hz-task-list' }, !active.length && note(t('noTasks')),
        ...active.map(j => h('details', { className: 'hz-task-row', key: j.id },
          h('summary', null, h('span', { className: 'hz-task-dot', 'data-status': importing(j) ? 'running' : j.status }), h('span', null, j.label || j.capability || j.id), h('small', null, t(importing(j) ? 'collectingResult' : j.status === 'blocked' ? 'waiting' : j.status))),
          h('div', { className: 'hz-task-detail' }, h(ComputeTaskDetail, { job: j, d, t }), j.detail && note(j.detail),
            h('div', { className: 'hz-actions' }, j.sessionId && button(t('open'), () => context.uiWorkspace.openSession(j.sessionId)),
              j.status === 'prepared' && button(t('submitCalculation'), () => d.act('project.submit-qe', { jobId: j.id, sessionId: j.sessionId }), d.busy || !d.state.resources.some(r => r.id === j.resource_id && r.enabled) || !d.state.operations.compute || !d.state.operations.network, true),
              importing(j) ? button(t('collectResult'), () => d.act('task.collect-qe', { jobId: j.id }), d.busy) : j.status === 'submission_unknown' ? button(t('checkSubmission'), () => d.act('task.refresh', { jobId: j.id }), d.busy) : button(t(j.status === 'prepared' ? 'discard' : 'stop'), () => d.act('task.cancel', { jobId: j.id }), d.busy))))),
        ...notices.map(j => h('div', { className: 'hz-task-notice', key: j.id, role: 'status' }, h('span', null, (j.label || j.id) + ' · ' + t(j.collection_status === 'failed' ? 'collectFailed' : j.status)), j.detail && note(j.detail),
          h(ComputeTaskDetail, { job: j, d, t }), h('div', { className: 'hz-actions' }, j.sessionId && button(t('open'), () => context.uiWorkspace.openSession(j.sessionId)),
            j.qe && !j.artifactId && button(t('collectResult'), () => d.act('task.collect-qe', { jobId: j.id }), d.busy),
            j.type === 'organize' && button(t('retry'), () => launchResources(d.sessionId, 'artifacts', { sessionId: j.sessionId, retryMessageIds: j.sourceMessageIds })),
            button(t('dismiss'), () => d.act('task.dismiss', { jobId: j.id }), d.busy)))));
    }
    function RevisionNode({ revision, d, t }) {
      const [files, setFiles] = useState(null), [fileDiff, setFileDiff] = useState(null), [picked, setPicked] = useState([]), [plan, setPlan] = useState(null);
      return h('details', { className: 'hz-revision', onToggle: event => { if (event.currentTarget.open && !files) d.act('project.diff', { revision: revision.revision }).then(value => value && setFiles(value.files)); } },
        h('summary', null, h('time', null, stamp(revision.time * 1000)), h('span', null, revision.message)),
        files && h('div', { className: 'hz-revision-files' }, !files.length && note(t('noChanges')), ...files.map(file => h('div', { className: 'hz-version-file', key: file }, !file.startsWith('.highzyme/') && h('input', { type: 'checkbox', 'aria-label': t('restoreVersion') + ': ' + file, checked: picked.includes(file), onChange: e => setPicked(old => e.target.checked ? [...old, file] : old.filter(v => v !== file)) }), button(file, () => fileDiff?.path === file ? setFileDiff(null) : d.act('project.fileDiff', { file, revision: revision.revision }).then(setFileDiff), d.busy)))),
        h('div', { className: 'hz-actions' }, ...['restore', 'undo'].map(mode => button(t(mode === 'restore' ? 'restoreVersion' : 'undoChange'), () => d.act('project.restorePreview', { revision: revision.revision, files: picked, mode }).then(setPlan), d.busy || !picked.length))),
        fileDiff && h(Difference, { value: fileDiff, t }),
        h(Modal, { open: !!plan, title: t('restorePreview'), onClose: () => setPlan(null), closeLabel: t('close'), className: 'hz-restore-dialog', contentClassName: 'hz-panel' }, plan && h(React.Fragment, null, ...plan.files.map(file => h('p', { key: file }, file)), plan.mode === 'undo' ? h('pre', { className: 'hz-patch' }, plan.patch) : plan.diffs.map(value => h(Difference, { key: value.path, value, t })), h(Notices, { d }), h('div', { className: 'hz-create-actions' }, button(t('cancel'), () => setPlan(null)), button(t('confirmRestore'), async () => { if (await d.act('project.restore', plan, t('versionSaved'))) { setPlan(null); setFileDiff(null); } }, d.busy, true)))));
    }
    function Difference({ value, t }) {
      if (value.binary || value.oldText?.includes('\0') || value.newText?.includes('\0')) return note(t('binary'));
      return h(DiffBlock, { diffs: [value], maxLines: 80, labels: { copy: t('copy'), copied: t('copied'), codeLabel: 'diff', wrapLabel: t('wrap'), unwrapLabel: t('nowrap'), collapseAria: t('collapse'), expandAria: n => t('expand') + ' (' + n + ')', collapse: t('collapse'), expand: n => t('expand') + ' (' + n + ')' } });
    }
    function Versions({ d, t }) {
      const [message, setMessage] = useState(''), [changes, setChanges] = useState(null), [picked, setPicked] = useState([]), [changesOpen, setChangesOpen] = useState(false);
      return h(React.Fragment, null,
        button(t('changes'), () => { if (changes !== null) setChangesOpen(!changesOpen); else d.act('project.diff').then(value => { if (value) { setChanges(value.files); setPicked([]); setChangesOpen(true); } }); }, d.busy),
        changes && h('form', { hidden: !changesOpen, className: 'hz-artifact-form', onSubmit: async event => { event.preventDefault(); if (await d.act('project.checkpoint', { message, paths: picked }, t('versionSaved'))) { setChanges(null); setChangesOpen(false); setPicked([]); setMessage(''); } } },
          h('strong', null, t('selectChanges')), !changes.length && note(t('noChanges')),
          ...changes.map(file => h('label', { className: 'hz-check', key: file }, h('input', { type: 'checkbox', checked: picked.includes(file), onChange: e => setPicked(old => e.target.checked ? [...old, file] : old.filter(v => v !== file)) }), file)),
          field(t('message'), input(message, setMessage, { required: true })), h(Button, { type: 'submit', size: 'sm', variant: 'primary', disabled: d.busy || !picked.length || !message.trim() }, t('checkpoint')), button(t('collapse'), () => setChangesOpen(false))),
        h('div', { className: 'hz-version-tree' }, !d.detail.history.length && note(t('noVersions')), ...d.detail.history.map(revision => h(RevisionNode, { key: revision.revision, revision, d, t }))));
    }
    function VersionView({ sessionId, t }) {
      const d = useData(sessionId);
      return h('section', { className: 'hz-panel hz-conversation-versions' }, h('header', { className: 'hz-heading' }, h('strong', null, t('versions')), refreshButton(d.refresh, d.busy, t)), h(Notices, { d }), d.detail && h(React.Fragment, null, h(Workarea, { d, t }), h(Versions, { key: sessionId + d.detail.path, d, t })));
    }
    function Workarea({ d, t }) {
      const [creating, setCreating] = useState(false), [name, setName] = useState(''), [comparison, setComparison] = useState(null), [confirm, setConfirm] = useState('');
      const row = d.detail.workarea;
      return h('section', { className: 'hz-workarea' }, h('div', { className: 'hz-toolbar' }, h('span', null, row?.active ? row.branch : t('mainWorkspace')), row ? h(Actions, { label: t('workarea'), items: [{ id: 'switch', label: t(row.active ? 'mainWorkspace' : 'enterWorkarea') }, { id: 'compare', label: t('compare') }, { id: 'merge', label: t('merge') }, { id: 'remove', label: t('removeWorkarea') }], onSelect: action => action === 'compare' ? d.act('workarea.compare').then(setComparison) : action === 'switch' ? d.act('workarea.switch', { active: !row.active }).then(changed) : setConfirm(action) }) : button(t('createWorkarea'), () => setCreating(true), d.busy)),
        comparison && h('details', { open: true }, h('summary', null, t('compare')), h('pre', { className: 'hz-patch' }, comparison.diff || t('noChanges')), button(t('close'), () => setComparison(null))),
        h(Modal, { open: creating, title: t('createWorkarea'), onClose: () => setCreating(false), closeLabel: t('close'), contentClassName: 'hz-panel', className: 'hz-create-dialog' }, h('form', { onSubmit: async e => { e.preventDefault(); if (await d.act('workarea.create', { name })) { setCreating(false); changed(); } } }, field(t('workareaName'), input(name, setName, { required: true, pattern: '[a-z0-9]+(-[a-z0-9]+)*' })), h(Notices, { d }), h('div', { className: 'hz-create-actions' }, button(t('cancel'), () => setCreating(false)), h(Button, { type: 'submit', variant: 'primary', disabled: d.busy }, t('create'))))),
        h(Modal, { open: !!confirm, title: t(confirm === 'merge' ? 'mergeConfirm' : 'removeConfirm'), onClose: () => setConfirm(''), closeLabel: t('close'), contentClassName: 'hz-panel' }, h(Notices, { d }), h('div', { className: 'hz-create-actions' }, button(t('cancel'), () => setConfirm('')), button(t(confirm === 'merge' ? 'merge' : 'remove'), async () => { if (await d.act('workarea.' + confirm)) { setConfirm(''); changed(); } }, d.busy, true))));
    }
    function Archives({ d, t }) {
      const [filter, setFilter] = useState('archived'), [query, setQuery] = useState(''), [selected, setSelected] = useState([]), [deleting, setDeleting] = useState(null), [deleteFiles, setDeleteFiles] = useState(false);
      const rows = d.detail.archives.filter(r => r.status === filter && r.title.toLowerCase().includes(query.toLowerCase()));
      const update = async (rows, status) => {
        const done = await d.act(async () => { for (const row of rows) await api('archive.update', { projectId: d.id, kind: row.kind, id: row.id, status }); return { ok: true }; });
        if (done) { setSelected([]); await context.sessions.refresh(); changed(); }
      };
      return h('section', null, h('div', { className: 'hz-toolbar' }, h(SegmentedTabs, { label: t('archiveManager'), value: filter, onChange: v => { setFilter(v); setSelected([]); }, items: ['archived', 'trash'].map(v => ({ value: v, label: t(v === 'trash' ? 'deleted' : v), id: 'archive-' + v, panelId: 'archive-list' })) })), input(query, setQuery, { placeholder: t('find'), 'aria-label': t('find') }),
        !!rows.length && h('div', { className: 'hz-toolbar' }, h('label', { className: 'hz-check' }, h('input', { type: 'checkbox', checked: rows.every(r => selected.includes(r.id)), onChange: e => setSelected(e.target.checked ? rows.map(r => r.id) : []) }), t('selectAll')), button(t('restore'), () => update(rows.filter(r => selected.includes(r.id)), 'active'), d.busy || !selected.length), filter === 'archived' ? button(t('trash'), () => update(rows.filter(r => selected.includes(r.id)), 'trash'), d.busy || !selected.length) : button(t('permanentDelete'), () => { setDeleting(rows.filter(r => selected.includes(r.id))); setDeleteFiles(false); }, d.busy || !selected.length)),
        !rows.length && note(t('archiveEmpty')), ...rows.map(row => h('article', { className: 'hz-archive-row', key: row.id }, h('input', { type: 'checkbox', 'aria-label': row.title, checked: selected.includes(row.id), onChange: e => setSelected(old => e.target.checked ? [...old, row.id] : old.filter(id => id !== row.id)) }), h('div', null, h('strong', null, row.title), h('small', null, t(row.kind === 'case' ? 'cases' : 'discussion') + (row.time ? ' · ' + stamp(row.time) : ''))), h(Actions, { label: t('projectActions'), items: [{ id: 'restore', label: t('restore') }, { id: filter === 'archived' ? 'trash' : 'delete', label: t(filter === 'archived' ? 'trash' : 'permanentDelete'), danger: true }], onSelect: action => action === 'delete' ? (setDeleting([row]), setDeleteFiles(false)) : update([row], action === 'restore' ? 'active' : 'trash') }))),
        h(Modal, { open: !!deleting, title: t('permanentDelete'), onClose: () => setDeleting(null), closeLabel: t('close'), contentClassName: 'hz-panel', className: 'hz-create-dialog' }, deleting && h(React.Fragment, null, note(t('deleteNotice')), ...deleting.map(row => h('p', { key: row.id }, row.title)), deleting.some(r => r.kind === 'case') && h('label', { className: 'hz-check' }, h('input', { type: 'checkbox', checked: deleteFiles, onChange: e => setDeleteFiles(e.target.checked) }), t('deleteFiles')), h(Notices, { d }), h('div', { className: 'hz-create-actions' }, button(t('cancel'), () => setDeleting(null)), button(t('permanentDelete'), async () => { const done = await d.act(async () => { for (const row of deleting) await api('archive.delete', { projectId: d.id, kind: row.kind, id: row.id, deleteFiles }); return { ok: true }; }); if (done) { setDeleting(null); setSelected([]); await context.sessions.refresh(); changed(); } }, d.busy, true)))));
    }
    function Memories({ d, t }) {
      const [rows, setRows] = useState([]), [query, setQuery] = useState(''), [form, setForm] = useState(null), [removing, setRemoving] = useState(null);
      const load = () => d.act('memory.list', { query }).then(value => value && setRows(value));
      useEffect(() => { load(); }, [d.id]);
      return h('section', null, h('div', { className: 'hz-toolbar' }, h('label', { className: 'hz-check' }, h('input', { type: 'checkbox', checked: !!d.detail.memory.enabled, disabled: d.busy, onChange: e => d.act('memory.enable', { enabled: e.target.checked }) }), t('memoryEnabled')), button(t('addMemory'), () => setForm({ title: '', content: '' }))),
        h('form', { className: 'hz-inline-form', onSubmit: e => { e.preventDefault(); load(); } }, input(query, setQuery, { placeholder: t('find'), 'aria-label': t('find') }), h(Button, { type: 'submit', variant: 'outline', size: 'sm' }, t('memorySearch'))),
        !rows.length && note(t('memoryEmpty')), ...rows.map(row => h('article', { className: 'hz-memory-row', key: row.id }, h('strong', null, row.title), h('p', null, row.content), h('small', null, stamp(row.updatedAt)), row.source?.sessionId && h('small', null, t('memorySource') + ': ' + (d.detail.cases.find(c => c.id === row.source.caseId)?.title || d.detail.sessionTitles[row.source.sessionId] || t('sourceDeleted'))), h('div', { className: 'hz-actions' }, button(t('edit'), () => setForm(row)), button(t('remove'), () => setRemoving(row.id))))),
        h(Modal, { open: !!form, title: t('memory'), onClose: () => setForm(null), closeLabel: t('close'), contentClassName: 'hz-panel', className: 'hz-create-dialog' }, form && h('form', { onSubmit: async e => { e.preventDefault(); if (await d.act('memory.save', form)) { setForm(null); load(); } } }, field(t('title'), input(form.title, title => setForm({ ...form, title }), { required: true })), field(t('body'), h('textarea', { value: form.content, rows: 6, required: true, onChange: e => setForm({ ...form, content: e.target.value }) })), h(Notices, { d }), h('div', { className: 'hz-create-actions' }, button(t('cancel'), () => setForm(null)), h(Button, { type: 'submit', variant: 'primary', disabled: d.busy }, t('save'))))),
        h(Modal, { open: !!removing, title: t('memoryDelete'), onClose: () => setRemoving(null), closeLabel: t('close'), contentClassName: 'hz-panel' }, h('div', { className: 'hz-create-actions' }, button(t('cancel'), () => setRemoving(null)), button(t('remove'), async () => { if (await d.act('memory.delete', { id: removing })) { setRemoving(null); load(); } }, d.busy, true))));
    }
    const pathMatches = (rule, file) => rule === '.' || file === rule || file.startsWith(rule.replace(/\/$/, '') + '/');
    const isAllowed = (value, file, operation) => {
      const score = list => Math.max(-1, ...list.filter(p => pathMatches(p, file)).map(p => p === '.' ? 0 : p.length));
      return Math.max(operation === 'read' && value.content === 'project' ? 0 : -1, score(value[operation])) > score(operation === 'read' ? value.denyRead : value.denyWrite);
    };
    function togglePath(value, file, operation, enabled) {
      const next = structuredClone(value), denied = operation === 'read' ? 'denyRead' : 'denyWrite';
      next[denied] = next[denied].filter(p => !pathMatches(file, p));
      next[operation] = next[operation].filter(p => !pathMatches(file, p));
      if (enabled) {
        next[operation].push(file);
      } else next[denied].push(file);
      return next;
    }
    function GrantChecks({ relative, paths = [relative], grant, t }) {
      return h('span', { className: 'hz-grant-checks', onClick: e => e.stopPropagation(), onKeyDown: e => e.stopPropagation() }, ...[['read', 'use'], ['write', 'modify']].map(([operation, label]) => {
        const allowed = paths.map(file => isAllowed(grant.value, file, operation));
        return h('label', { key: operation, title: t(label) + ': ' + relative }, h('input', { type: 'checkbox', 'aria-label': t(label) + ': ' + relative, ref: node => { if (node) node.indeterminate = allowed.some(Boolean) && !allowed.every(Boolean) || paths.length === 1 && [...grant.value[operation], ...(operation === 'read' ? grant.value.denyRead : grant.value.denyWrite)].some(p => p !== relative && pathMatches(relative, p)); }, checked: allowed.every(Boolean), disabled: grant.busy, onChange: e => grant.save(paths.reduce((value, file) => togglePath(value, file, operation, e.target.checked), grant.value)) }), h('span', null, t(label + 'Short')));
      }));
    }
    function FileGrant({ absolutePath }) {
      const grant = useContext(GrantsContext); if (!grant) return null;
      const root = grant.d.detail.path.replaceAll('\\', '/'), file = absolutePath.replaceAll('\\', '/');
      return h(GrantChecks, { relative: file.slice(root.length + 1), grant, t: grant.t });
    }
    function FileActions({ absolutePath, sessionId, t }) {
      const grant = useContext(GrantsContext), [notice, setNotice] = useState(''), [resultAction, setResultAction] = useState(null);
      useEffect(() => { if (notice) { const timer = setTimeout(() => setNotice(''), 2800); return () => clearTimeout(timer); } }, [notice]);
      const root = grant?.d.detail.path.replaceAll('\\', '/'), file = root && absolutePath.replaceAll('\\', '/').slice(root.length + 1);
      const artifact = grant?.d.detail.artifacts.find(a => a.files?.result === file || a.relatedFiles?.includes(file));
      const allowed = grant && isAllowed(grant.value, file, 'read');
      useEffect(() => {
        setResultAction(null);
        if (!allowed || !file.endsWith('-result.json')) return;
        if (artifact?.analysis?.replot !== undefined) { setResultAction(artifact.analysis.replot ? 'replotRates' : null); return; }
        let active = true;
        api('file.analysisAction', { projectId: grant.d.id, sessionId, file }).then(value => { if (active) setResultAction(value.action); }).catch(() => {});
        return () => { active = false; };
      }, [root, file, allowed, artifact?.updatedAt]);
      if (!grant) return null;
      const extension = absolutePath.split('.').pop().toLowerCase();
      const kinds = absolutePath.endsWith('-evidence.json') ? ['compareEvidence'] : absolutePath.endsWith('-result.json') ? resultAction ? [resultAction] : [] : ['pdf', 'docx'].includes(extension) ? ['readPaper'] : ['mol', 'sdf', 'cif', 'mmcif', 'pdb', 'xyz', 'extxyz', 'vasp', 'poscar', 'contcar'].includes(extension) || /[\\/](POSCAR|CONTCAR)$/i.test(absolutePath) ? ['checkStructure'] : ['csv', 'tsv', 'xlsx'].includes(extension) ? ['fitRates', 'analyzeSignal'] : ['png', 'jpg', 'jpeg', 'webp'].includes(extension) ? ['measureColor'] : [];
      if (!kinds.length) return null;
      const prepare = kind => {
        const binding = context.sessions.binding(sessionId);
        const result = binding && context.get('conversation')?.input.requestDraftInitialization(binding, { prompt: t(kind + 'Prompt') + '\n' + file });
        setNotice(result === 'applied' ? t('taskPrepared') : t('draftOccupied'));
      };
      return h('span', { className: 'hz-file-action', onClick: e => e.stopPropagation() },
        kinds.length > 1 ? h(Actions, { label: t('fileAnalysis'), items: kinds.map(kind => ({ id: kind, label: t(kind), disabled: !isAllowed(grant.value, file, 'read') })), onSelect: prepare }) : h(Button, { variant: 'ghost', size: 'sm', disabled: !isAllowed(grant.value, file, 'read'), title: t(kinds[0]), 'aria-label': t(kinds[0]) + ': ' + file, onClick: () => prepare(kinds[0]) }, t(kinds[0])),
        notice && h('small', { role: 'status' }, notice));
    }
    function Access({ d, t, grant }) {
      const value = grant.value;
      return h('section', { className: 'hz-access' },
        field(t('policy'), h('select', { value: value.content, disabled: grant.busy, onChange: e => grant.save({ ...value, content: e.target.value, denyRead: [], read: [] }) }, option('project', t('fullProject')), option('selected', t('selectedOnly')))),
        h('div', { className: 'hz-permission-heading' }, h('span', null, t('allProject')), h(GrantChecks, { relative: '.', grant, t })),
        h('details', null, h('summary', null, t('advanced')), h(AdvancedAccess, { d, t, grant })),
        !!d.detail.artifacts.length && h('details', { className: 'hz-artifact-grants' }, h('summary', null, t('artifactPermissions')), ...d.detail.artifacts.map(a => h('div', { key: a.id, className: 'hz-permission-heading' }, h('span', { title: a.file }, a.title), h(GrantChecks, { relative: a.file, paths: [...new Set([...(a.relatedFiles || [a.file]), ...d.detail.cases.flatMap(c => c.references.filter(r => r.artifactId === a.id).flatMap(r => r.relatedFiles || [r.file]))])], grant, t })))));
    }
    function AdvancedAccess({ d, t, grant }) {
      const [value, setValue] = useState(grant.value);
      useEffect(() => setValue(grant.value), [grant.value]);
      return h('form', { onSubmit: e => { e.preventDefault(); grant.save(value); } }, ...['read', 'write'].map(key => field(t(key === 'read' ? 'readPaths' : 'writePaths'), h('textarea', { value: value[key].join('\n'), rows: 3, onChange: e => setValue({ ...value, [key]: e.target.value.split('\n') }) }))), h(Button, { type: 'submit', variant: 'outline', size: 'sm', disabled: d.busy }, t('save')));
    }
    const resourceTabs = ['files', 'artifacts', 'access', 'tasks', 'archiveManager', 'memory'];
    function ResourceManager({ sessionId, renderFiles, t }) {
      const d = useData(sessionId), initialTab = panelPreferences(d.id).tab || 'files';
      const [selectedTab, setTab] = useState(initialTab), [visited, setVisited] = useState([initialTab]), [optimistic, setOptimistic] = useState(null), [showLocation, setShowLocation] = useState(false), [manageCases, setManageCases] = useState(false), [fileRefresh, setFileRefresh] = useState(0);
      const tab = resourceTabs.includes(selectedTab) ? selectedTab : 'files';
      const initialView = useMemo(() => panelPreferences(d.id).fileView, [d.id]);
      const saveFileView = useCallback(value => savePanelPreferences(d.id, { fileView: value }), [d.id]);
      const selectTab = useCallback(value => { setTab(value); savePanelPreferences(d.id, { tab: value }); if (value === 'artifacts') d.refresh(); }, [d.id, d.refresh]);
      useEffect(() => { setOptimistic(null); setTab(panelPreferences(d.id).tab || 'files'); setVisited([panelPreferences(d.id).tab || 'files']); }, [d.id]);
      useEffect(() => { setVisited(old => old.includes(tab) ? old : [...old, tab]); }, [tab]);
      useEffect(() => { const update = event => { if (event.detail.projectId === d.id) selectTab(event.detail.tab); }; window.addEventListener('highzyme:navigate', update); return () => window.removeEventListener('highzyme:navigate', update); }, [d.id, selectTab]);
      if (!d.detail || d.detail.id !== d.id) return h('section', { className: 'hz-panel hz-manager' }, h(Notices, { d }), note(t('empty')));
      const refreshPanel = () => d.act(async () => { if (['files', 'access'].includes(tab)) setFileRefresh(n => n + 1); if (tab === 'tasks') await Promise.all(d.detail.jobs.filter(j => j.type === 'compute' && ['running', 'queued'].includes(j.status)).map(j => api('task.refresh', { projectId: d.id, jobId: j.id }))); });
      const grant = { d, t, value: optimistic || d.detail.access, busy: d.busy, save: async value => { setOptimistic(value); const result = await d.act('access.save', value, t('permissionsUpdated')); setOptimistic(null); changed(); return result; } };
      return h(GrantsContext.Provider, { value: grant }, h('section', { className: 'hz-panel hz-manager' },
        h('header', { className: 'hz-heading' }, h('strong', null, d.project.name), h('div', { className: 'hz-actions' }, refreshButton(refreshPanel, d.busy, t), h(Actions, { label: t('projectActions'), items: [{ id: 'cases', label: t('manageCases') }, { id: 'location', label: t('location') }, { id: 'copy', label: t('copyPath') }], onSelect: id => id === 'cases' ? setManageCases(true) : id === 'location' ? setShowLocation(!showLocation) : d.act(() => navigator.clipboard.writeText(d.detail.path), {}, t('copied')) }))),
        showLocation && note(d.detail.path),
        h('nav', { className: 'hz-tabs hz-main-tabs' }, ...resourceTabs.map(v => h('button', { key: v, type: 'button', className: tab === v ? 'is-active' : '', onClick: () => selectTab(v) }, t(v === 'access' ? 'permissions' : v)))),
        h(Notices, { d }),
        tab === 'access' && h(Access, { d, t, grant }),
        h('div', { className: 'hz-native-files' + (tab === 'access' ? ' hz-permission-files' : ''), hidden: !['files', 'access'].includes(tab) }, renderFiles({ permissionsOnly: tab === 'access', refreshKey: fileRefresh, initialView, onViewChange: saveFileView })),
        ...Object.entries({ artifacts: Artifacts, tasks: Tasks, archiveManager: Archives, memory: Memories }).map(([key, Component]) => h('div', { key, hidden: tab !== key }, visited.includes(key) && h(Component, { key: d.id, d, t, grant, active: tab === key }))),
        h(Modal, { open: manageCases, onClose: () => setManageCases(false), title: t('manageCases'), closeLabel: t('close'), className: 'hz-cases-dialog', contentClassName: 'hz-panel hz-modal-content' }, h(CaseList, { d, t }))));
    }
    function DefaultModel({ t }) {
      const directory = useMemo(() => createSnapshotStore({ current: null, groups: [], failures: [], routable: null, status: 'loading', pending: null, error: null }), []);
      const [notice, setNotice] = useState('');
      const install = value => directory.set({ current: value.default.provider && value.default.model ? value.default : null, groups: value.groups, failures: value.failures,
        routable: value.groups.some(group => group.id === value.default.provider && group.models.some(model => model.id === value.default.model)), status: 'ready', pending: null, error: null });
      const load = useCallback(async () => { try { install(await api('model.catalog')); } catch (error) { directory.set({ ...directory.getSnapshot(), status: 'error', error }); } }, [directory]);
      useEffect(() => {
        load();
        const remote = context.get('remote');
        const subscriptions = ['settings/document-updated', 'credentials/record-updated', 'llm/adapters-updated'].map(name => remote.$on(name, load));
        return () => subscriptions.forEach(dispose => dispose());
      }, [load]);
      const select = async value => {
        directory.set({ ...directory.getSnapshot(), status: 'selecting', pending: value });
        try {
          install(await api('model.default', value)); setNotice(t('saved'));
          await context.get('modelDirectories').catalog.refresh();
          return { ok: true };
        } catch (error) {
          directory.set({ ...directory.getSnapshot(), status: 'ready', pending: null });
          return { ok: false, error: { code: 'model/save-failed', message: error.message } };
        }
      };
      return h('section', { className: 'hz-default-model' }, h('div', { className: 'hz-resource-heading' }, h('span', null, t('defaultModel')),
        h(ModelSelect, { available: true, directory, load, select, t: context.locale.bind('model'), renderSlot: (_name, _props, options) => options?.fallback ?? null })), notice && h('small', { role: 'status' }, notice));
    }
    function AccessSettings({ t, renderSlot }) {
      const d = useData();
      const operations = d.state.operations || {};
      const save = values => d.act('operations.save', { ...operations, ...values }, t('operationsUpdated')).then(changed);
      return h('section', { className: 'hz-panel hz-settings' }, h(Notices, { d }),
        renderSlot('highzyme.settings.default-permission', {}),
        ...['shell', 'network', 'compute'].map(key => h('label', { className: 'hz-check', key }, h('input', { type: 'checkbox', checked: !!operations[key], disabled: d.busy || key === 'compute' && !d.state.resources.some(r => r.enabled), onChange: e => save({ [key]: e.target.checked }) }), t(key))),
        d.detail && operations.shell && !d.detail.access.shell && note(t('shellLimited')));
    }
    function ManagerLauncher({ t }) {
      useEffect(() => { const id = activeSession(); if (id) launchResources(id); }, []);
      return h('section', { className: 'hz-panel' }, note(t('empty')));
    }
    async function launchComputeSetup(d, t, close, resource) {
      const previous = await api('resource.assistant', { id: resource?.id });
      await context.sessions.refresh();
      const workspaces = context.workspaces.list.getSnapshot(), sessions = context.sessions.list.getSnapshot();
      let id = previous.sessionId;
      const reusable = sessions.byId[id] && !workspaces.archivedSessionIds.includes(id) && workspaces.items.some(p => p.sessionIds.includes(id));
      if (!reusable) {
        const workspaceId = projectForNewConversation(workspaces, sessions, d.id);
        if (!workspaceId) throw new Error(t('empty'));
        id = await context.sessions.create({ workspaceId, agentPreset: 'research' });
      }
      const reference = context.sessions.retain(id, { source: 'controllerOperation' });
      try {
        await reference.ready;
        const binding = context.sessions.binding(id);
        const prompt = resource ? t('resumeSetupPrompt') + '\n' + JSON.stringify({ resource_id: resource.id, name: resource.name, probe: resource.probe }, null, 2) : t('computeSetupPrompt');
        const conversation = context.get('conversation');
        const model = await context.modelDirectories.directoryFor(id).load();
        const initialized = conversation.input.requestDraftInitialization(binding, { prompt });
        await api('resource.assistant', { id: resource?.id, setupSessionId: id });
        publishCatalog(await api('state'));
        close(); currentSession = id; context.uiWorkspace.openSession(id);
        const composer = conversation.input.for(binding.ctx);
        if (initialized === 'blocked') composer.notify('info', t('setupBusy'));
        else if (initialized === 'preserved') composer.notify('info', t('draftOccupied'));
        else if (!model.current?.provider || !model.current?.model || !model.routable) composer.notify('error', t('modelRequired'));
        else composer.submit();
      } finally { reference.release(); }
    }
    function ResourceHealth({ probe, ssh, t }) {
      return h('div', { className: 'hz-resource-health', role: 'status' },
        ...(!probe ? ['pendingSetup'] : [probe.connected || probe.ready ? 'connected' : 'pendingSetup', probe.ready ? 'submissionReady' : 'submissionUnavailable', ...(ssh ? [probe.capabilities?.includes('quantum_espresso') ? 'qeAvailable' : 'qeUnavailable'] : [])]).map(key => h('span', { key, className: 'hz-compute-status', 'data-ready': ['connected', 'submissionReady', 'qeAvailable'].includes(key) }, t(key))));
    }
    function Compute({ t, close }) {
      const d = useData(), [form, setForm] = useState(null), [inspection, setInspection] = useState(null), [pendingEnabled, setPendingEnabled] = useState({}), [opening, setOpening] = useState(null);
      const openAssistant = async resource => {
        setOpening(resource?.id || 'new');
        try { await d.act(() => launchComputeSetup(d, t, close, resource)); }
        finally { setOpening(null); }
      };
      const change = (key, value) => { setForm(old => ({ ...old, [key]: value })); if (['host', 'port', 'user', 'identity_file'].includes(key)) setInspection(null); else if (['setup_script', 'remote_root', 'qe_command'].includes(key)) setInspection(old => old && { ...old, ready: false, needsCheck: true }); };
      const edit = row => { setForm({ transport: 'ssh', name: '', host: '', port: '', user: '', identity_file: '', qe_command: 'pw.x', ...row, token: '' }); setInspection(row?.probe || null); };
      const inspect = async () => {
        const found = await d.act('resource.inspect', form);
        if (!found) return;
        setInspection(found);
        setForm(old => ({ ...old, remote_root: old.remote_root || found.remote_root, port: old.port || Number(found.connection?.port) || '',
          partition: old.partition || (found.partitions?.length === 1 ? found.partitions[0].name : ''),
          account: old.account || (found.associations?.length === 1 ? found.associations[0].account : '') }));
      };
      const save = async e => {
        e.preventDefault();
        const row = await d.act('resource.save', form);
        if (row && await d.act('resource.probe', { id: row.id }, t('saved'))) { setForm(null); setInspection(null); }
      };
      const entry = (key, extra = {}) => field(t(key === 'name' ? 'title' : key === 'user' ? 'username' : key), input(form[key] || '', value => change(key, value), extra));
      const policyField = (kind, key) => field(t(key), input(form[kind]?.[key] ?? (kind === 'defaults' ? d.state.jobDefaults[key] : ''),
        value => setForm(old => ({ ...old, [kind]: { ...old[kind], [key]: value === '' ? '' : Number(value) } })),
        { type: 'number', min: 1, step: 1, required: kind === 'defaults', placeholder: kind === 'limits' ? t('noLimit') : undefined }));
      return h('section', { className: 'hz-compute' }, h('div', { className: 'hz-toolbar hz-actions' }, button(t(opening === 'new' ? 'openingSetup' : 'setupAssistant'), () => openAssistant(), d.busy, true), button(t('connectCompute'), () => edit(), d.busy)), h(Notices, { d }), !d.state.resources.length && note(t('noCompute')),
        ...d.state.resources.map(r => h('article', { className: 'hz-resource', key: r.id }, h('div', { className: 'hz-resource-heading' }, h('strong', null, r.name), h(ResourceHealth, { probe: r.probe, ssh: r.transport === 'ssh', t })),
          note(r.transport === 'ssh' ? r.host + ' · Slurm' + (r.partition ? ' · ' + r.partition : '') : r.url),
          !!r.probe?.capabilities?.length && note(r.probe.capabilities.map(key => ({ quantum_espresso: 'Quantum ESPRESSO', python: 'Python', shell: 'Shell', psi4: 'Psi4', cp2k: 'CP2K', lammps: 'LAMMPS' })[key] || key).join(' · ')), ...[r.probe?.error, ...(r.probe?.issues || []), r.probe?.environment_error].filter(Boolean).map((message, i) => h('p', { className: 'hz-error', key: i }, message)),
          r.lastCalculation && note(t('lastCalculation') + ' · ' + t(r.lastCalculation.converged ? r.lastCalculation.method ? 'calculationCompleted' : 'calculationPassed' : 'calculationFailed') + ' · ' + stamp(r.lastCalculation.time)),
          h('div', { className: 'hz-resource-heading' }, h('div', { className: 'hz-actions' }, r.transport === 'ssh' && button(t(opening === r.id ? 'openingSetup' : 'continueSetup'), () => openAssistant(r), d.busy), button(t('check'), () => d.act('resource.probe', { id: r.id }), d.busy), button(t('edit'), () => edit(r), d.busy), button(t('remove'), () => d.act('resource.remove', { id: r.id }), d.busy), r.transport === 'ssh' && r.probe?.capabilities?.includes('quantum_espresso') && button(t('testCalculation'), () => d.act('project.compute-test', { resourceId: r.id, language: t('save') === '保存' ? 'zh' : 'en' }), d.busy || !d.id || !r.enabled || !d.state.operations.compute || !d.state.operations.network)),
            h('label', { className: 'hz-check' }, h('input', { type: 'checkbox', checked: pendingEnabled[r.id] ?? r.enabled, disabled: d.busy || !r.probe?.ready, onChange: async e => { const enabled = e.target.checked; setPendingEnabled(old => ({ ...old, [r.id]: enabled })); try { await d.act('resource.enable', { id: r.id, enabled }); } finally { setPendingEnabled(old => { const next = { ...old }; delete next[r.id]; return next; }); } } }), t('enabled'))))),
        h(Modal, { open: !!form, title: t(form?.id ? 'edit' : 'connectCompute'), onClose: () => !d.busy && setForm(null), closeLabel: t('close'), className: 'hz-compute-dialog', contentClassName: 'hz-panel hz-modal-content' }, form && h('form', { onSubmit: save },
          !form.id && h(SegmentedTabs, { label: t('connection'), value: form.transport, onChange: value => { change('transport', value); setInspection(null); }, items: ['ssh', 'http'].map(v => ({ id: 'compute-' + v, value: v, label: t(v === 'ssh' ? 'sshResource' : 'httpResource'), panelId: 'compute-connection' })) }),
          entry('name', { placeholder: form.host || '' }),
          form.transport === 'ssh' ? h(React.Fragment, null,
            h('div', { className: 'hz-compute-grid' }, entry('host', { required: true, placeholder: 'my-cluster' }), field(t('port'), input(form.port || '', value => change('port', value === '' ? '' : Number(value)), { type: 'number', min: 1, max: 65535, placeholder: '22' }))),
            field(t('username'), input(form.user, value => change('user', value), { placeholder: t('sshConfigHint') })),
            field(t('privateKey'), h('div', { className: 'hz-key-picker' }, input(form.identity_file, value => change('identity_file', value), { placeholder: t('sshConfigHint'), autoComplete: 'off' }), button(t('selectKey'), async () => { const selected = await d.act('resource.choose-key'); if (selected?.file) change('identity_file', selected.file); }, d.busy))),
            button(t('inspectEnvironment'), inspect, d.busy || !form.host),
            inspection && h('div', { className: 'hz-inspection' }, h(ResourceHealth, { probe: inspection, ssh: true, t }), ...(inspection.issues || []).map(message => h('p', { className: 'hz-error', key: message }, message)),
              inspection.environment_error && h('p', { className: 'hz-error' }, inspection.environment_error),
              !!inspection.qe_modules?.length && field(t('qeModule'), h('select', { value: inspection.qe_modules.find(m => form.setup_script?.includes(m)) || '', onChange: e => change('setup_script', e.target.value ? 'module purge\nmodule load ' + e.target.value : '') }, option('', t('automatic')), ...inspection.qe_modules.map(m => option(m, m))))),
            h('details', { className: 'hz-compute-advanced' }, h('summary', null, t('computeDetails')),
              h('div', { className: 'hz-compute-grid' }, field(t('partition'), inspection?.partitions?.length ? h('select', { value: form.partition || '', onChange: e => change('partition', e.target.value) }, option('', '—'), ...inspection.partitions.map(p => option(p.name, p.name))) : input(form.partition || '', value => change('partition', value))), field(t('account'), input(form.account || '', value => change('account', value)))),
              field(t('qos'), input(form.qos || '', value => change('qos', value))), field(t('remoteRoot'), input(form.remote_root || '', value => change('remote_root', value), { placeholder: '~/.highzyme/jobs' })),
              field(t('qeCommand'), input(form.qe_command || '', value => change('qe_command', value), { placeholder: 'pw.x' })),
              field(t('setupScript'), h('textarea', { value: form.setup_script || '', rows: 3, onChange: e => change('setup_script', e.target.value) })),
              h('div', { className: 'hz-compute-grid' }, field(t('pythonCommand'), input(form.python_command || '', value => change('python_command', value), { placeholder: 'python3' })), field(t('mpiCommand'), input(form.mpi_command || '', value => change('mpi_command', value), { placeholder: 'srun' }))),
              h('div', { className: 'hz-compute-grid' }, ...['dos', 'projwfc', 'bands', 'pp', 'neb', 'bader'].map(key => field(key === 'bader' ? 'Bader' : key + '.x', input(form.program_commands?.[key] || '', value => { setForm(old => ({ ...old, program_commands: { ...old.program_commands, [key]: value } })); setInspection(null); }, { placeholder: inspection?.programs?.[key] || (key === 'bader' ? 'bader' : key + '.x') })))))
          ) : h(React.Fragment, null, field(t('url'), input(form.url || '', value => change('url', value), { type: 'url', required: true })), field(t('token'), input(form.token, value => change('token', value), { type: 'password', autoComplete: 'new-password', placeholder: t('tokenHint') }))),
          ...(form.transport === 'ssh' ? ['defaults', 'limits'] : []).map(kind => h('details', { className: 'hz-compute-advanced', key: kind }, h('summary', null, t(kind === 'defaults' ? 'jobDefaults' : 'jobLimits')), h('div', { className: 'hz-compute-grid' }, ...Object.keys(d.state.jobDefaults || {}).map(key => policyField(kind, key))))),
          h(Notices, { d }), h('div', { className: 'hz-create-actions' }, button(t('cancel'), () => setForm(null), d.busy), h(Button, { type: 'submit', variant: 'primary', size: 'sm', disabled: d.busy || form.transport === 'ssh' && (!inspection?.connected || inspection.needsCheck) }, t('save'))))));
    }
    function NativeTools({ t, renderSlot, close }) {
      const [tab, setTab] = useState('compute');
      return h('section', { className: 'hz-panel hz-settings' }, h('nav', { className: 'hz-tabs' }, ...['compute', 'search', 'subagents', 'terminal', 'advanced'].map(v => h('button', { key: v, type: 'button', className: tab === v ? 'is-active' : '', onClick: () => setTab(v) }, t(v === 'compute' ? 'computeTab' : v)))),
        tab === 'compute' ? h(Compute, { t, close }) : renderSlot('plugins.item', { view: 'page' }, { only: ({ search: 'web-search', subagents: 'subagent', terminal: 'shell', advanced: 'agent-loop' })[tab] }));
    }
    function CaseResearchEditor({ sessionId, t, onClose }) {
      const d = useData(sessionId), [state, setState] = useState(null), [workflows, setWorkflows] = useState({}), [validations, setValidations] = useState({ tasks: [], results: [] }), [selectedCandidate, setSelectedCandidate] = useState(''), [form, setForm] = useState({ kind: 'general', objective: '', constraints: '' });
      useEffect(() => {
        if (!d.id) return;
        d.act(async () => { const value = await api('case.research', { projectId: d.id, sessionId }); setWorkflows(value.workflows); setValidations(value.validations); setState(value.research); setForm({ kind: value.research.kind, objective: value.research.objective, constraints: value.research.constraints.join('\n') }); });
      }, [d.id, sessionId]);
      const save = async () => {
        const value = await d.act('case.research.save', { operation: 'configure', kind: form.kind, objective: form.objective, constraints: form.constraints.split('\n').filter(v => v.trim()), language: t('save') === zh.save ? 'zh' : 'en' }, t('saved'));
        if (value) setState(value); return value;
      };
      const prepare = async () => {
        if (!await save()) return;
        const binding = context.sessions.binding(sessionId);
        const candidate = state.candidates.find(c => c.id === selectedCandidate);
        const task = [t('prepareResearchPrompt'), form.objective, form.constraints, candidate && [t('selectedCandidate') + ': ' + candidate.title, t('proposalVersion') + ': ' + candidate.proposal_revision, candidate.hypothesis, t('validationQuestion') + ': ' + (candidate.validation?.method || ''), t('validationCriterion') + ': ' + (candidate.validation?.criterion || '')].join('\n')].filter(Boolean).join('\n\n');
        const value = binding && context.get('conversation')?.input.requestDraftInitialization(binding, { prompt: task });
        if (value === 'applied') onClose();
        else await d.act(async () => null, {}, t('draftOccupied'));
      };
      const openEvidence = ref => d.act(async () => {
        const c = d.project.cases.find(c => c.sessions.includes(sessionId));
        const saved = await api('artifact.file', { projectId: d.id, sessionId, ...(c.references.some(r => r.artifactId === ref.artifact_id) ? { caseId: c.id } : {}), artifactId: ref.artifact_id, file: ref.file });
        await openFiles(d.id, saved.file); onClose();
      });
      return h('div', null, h(Notices, { d }), !state ? note(t('loading')) : h(React.Fragment, null,
        field(t('workflowKind'), h('select', { value: form.kind, onChange: e => setForm({ ...form, kind: e.target.value }) }, ...Object.keys(workflows).map(kind => h('option', { key: kind, value: kind }, t(kind))))),
        field(t('researchObjective'), h('textarea', { rows: 3, value: form.objective, onChange: e => setForm({ ...form, objective: e.target.value }) })),
        field(t('researchRequirements'), h('textarea', { rows: 3, value: form.constraints, onChange: e => setForm({ ...form, constraints: e.target.value }) })),
        h('nav', { className: 'hz-research-steps', 'aria-label': t('researchWorkflow') }, ...(workflows[state.kind]?.steps || []).map(step => h(Button, { key: step, variant: state.stage === step ? 'primary' : 'outline', size: 'sm', disabled: d.busy, onClick: async () => { const next = await d.act('case.research.save', { operation: 'stage', stage: step }); if (next) setState(next); } }, t('stage_' + step)))),
        !state.candidates.length ? note(t('noCandidates')) : state.candidates.map(c => h('details', { key: c.id, className: 'hz-research-candidate' }, h('summary', null, h('strong', null, c.title), h('span', { className: 'hz-value-state' }, t(c.status))),
          h('p', null, t('proposalStatus') + ': ' + t(c.status) + ' · ' + t('validationOutcome') + ': ' + t(c.validation_outcome)),
          note(t('proposalVersion') + ': ' + c.proposal_revision.slice(0, 8)),
          c.based_on && note(t('basedOnApplication') + ': ' + c.based_on.title + ' · ' + c.based_on.candidate_revision.slice(0, 8)),
          h('p', null, c.hypothesis), h('p', null, c.design || c.application), h('p', null, t('baseline') + ': ' + c.baseline),
          c.screening && h('div', null, h('strong', null, t('compositionChecks')), h('ul', null, ...c.screening.checks.map(check => h('li', { key: check.name }, t(check.name) + ': ' + t(check.status) + (check.net_charge !== undefined ? ' · ' + t('netCharge') + ': ' + check.net_charge : ''))))),
          c.uncertainties.length > 0 && h('div', null, h('strong', null, t('uncertainties')), h('ul', null, ...c.uncertainties.map((s, i) => h('li', { key: i }, s)))),
          h('p', null, [c.validation?.method, c.validation?.comparison, c.validation?.criterion].filter(Boolean).join(' · ')),
          ...c.evidence.map(ref => h('div', { key: ref.artifact_id }, button(ref.file.split('/').pop(), () => openEvidence(ref)))),
          ...c.feedback.map((feedback, i) => h('div', { key: i }, h('p', null, t(feedback.outcome) + ': ' + feedback.summary), feedback.candidate_revision !== c.proposal_revision && note(feedback.candidate_revision ? t('previousProposal') + ' · ' + feedback.candidate_revision.slice(0, 8) : t('unrecordedVersion')), button(feedback.source.file.split('/').pop(), () => openEvidence(feedback.source)))),
          ...validations.tasks.filter(j => j.validation.candidate_id === c.id).map(j => h('details', { key: j.id }, h('summary', null, t(j.status) + ' · ' + j.label), note(t('proposalVersion') + ': ' + j.validation.candidate_revision.slice(0, 8)), h('p', null, j.validation.question), h('p', null, t('validationCriterion') + ': ' + j.validation.criterion))),
          ...validations.results.filter(a => a.validation.candidate_id === c.id && !c.feedback.some(f => f.source.artifact_id === a.id && f.source.revision === a.revision)).map(a => h('div', { key: a.id }, button(a.title, () => openEvidence({ artifact_id: a.id, file: a.file })), note(t('proposalVersion') + ': ' + a.validation.candidate_revision.slice(0, 8)))))),
        state.candidates.length > 0 && field(t('selectedCandidate'), h('select', { value: selectedCandidate, onChange: e => setSelectedCandidate(e.target.value) }, h('option', { value: '' }, t('allCandidates')), ...state.candidates.map(c => h('option', { key: c.id, value: c.id }, c.title)))),
        h('div', { className: 'hz-create-actions' }, button(t('close'), onClose), button(t('save'), save, d.busy), button(t('prepareResearch'), prepare, d.busy || !form.objective.trim(), true))));
    }
    function HeaderActions({ sessionId, t }) {
      const state = useSyncExternalStore(subscribe, () => catalog), [researchOpen, setResearchOpen] = useState(false);
      const c = state.projects.find(p => p.sessions.includes(sessionId))?.cases.find(c => c.sessions.includes(sessionId));
      useEffect(() => { currentSession = sessionId; api('state').then(publishCatalog); }, [sessionId]);
      return h('div', { className: 'hz-header-actions' },
        c && button(t('researchWorkflow'), () => setResearchOpen(true)),
        button(t('fromConversation'), () => launchResources(sessionId, 'artifacts', { sessionId })),
        h(Modal, { open: researchOpen, onClose: () => setResearchOpen(false), title: t('researchWorkflow'), closeLabel: t('close'), className: 'hz-research-dialog', contentClassName: 'hz-panel hz-modal-content' }, researchOpen && h(CaseResearchEditor, { sessionId, t, onClose: () => setResearchOpen(false) })));
    }
    function NewItemDialog({ t, useWorkspaces, useSessions }) {
      const [creating, setCreating] = useState(false), [title, setTitle] = useState(''), [folderName, setFolderName] = useState(''), [kind, setKind] = useState('discussion'), [workflowKind, setWorkflowKind] = useState('general'), [projectHint, setProjectHint] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false);
      const workspaces = useWorkspaces(s => s), sessions = useSessions(s => s);
      const ready = workspaces.phase === 'ready' && sessions.phase === 'ready';
      const projectId = projectForNewConversation(workspaces, sessions, projectHint);
      const selectedProject = workspaces.items.find(p => p.workspaceId === projectId);
      const loadError = workspaces.error?.message || sessions.error?.message;
      const failure = error || loadError;
      const failureMessage = /failed to ensure project directory|workspace\/invalid-path/.test(failure || '') ? t('projectDirectoryUnavailable') : t(error ? 'createFailed' : 'projectLoadFailed');
      useEffect(() => { const open = event => { setCreating(true); setWorkflowKind('general'); setProjectHint(event.detail?.projectId || ''); setKind(event.detail?.kind || 'discussion'); setError(''); }; window.addEventListener('highzyme:new', open); return () => window.removeEventListener('highzyme:new', open); }, []);
      if (!creating) return null;
      return h(Modal, { open: creating, onClose: () => { if (!busy) setCreating(false); }, title: t('newItem'), closeLabel: t('close'), className: 'hz-create-dialog', contentClassName: 'hz-panel hz-modal-content' }, h('form', { onSubmit: async e => {
          e.preventDefault(); setBusy(true); setError('');
          try {
            if (!projectId) throw new Error(t('empty'));
            const c = kind === 'cases' ? await api('case.create', { projectId, title, folderName, workflowKind }) : null;
            const id = await context.sessions.create({ workspaceId: projectId, agentPreset: 'research' });
            const ref = context.sessions.retain(id, { source: 'controllerOperation' });
            try { await ref.ready; if (c) await api('case.attach', { projectId, caseId: c.id, sessionId: id }); } finally { ref.release(); }
            await context.sessions.refresh(); publishCatalog(await api('state')); setCreating(false); setTitle(''); setFolderName(''); context.uiWorkspace.openSession(id);
          } catch (e) { setError(e.message); } finally { setBusy(false); }
        } }, field(t('project'), h('span', null, ready ? selectedProject?.title || t('empty') : t('loading'))), h(SegmentedTabs, { label: t('newItem'), value: kind, onChange: setKind, items: ['discussion', 'cases'].map(v => ({ value: v, label: t(v), id: 'new-' + v, panelId: 'new-fields' })) }), kind === 'cases' && h('div', { id: 'new-fields', role: 'tabpanel', 'aria-labelledby': 'new-cases' }, field(t('title'), input(title, setTitle, { required: true, 'data-modal-autofocus': true })), field(t('caseFolder'), input(folderName, setFolderName, { pattern: '[a-z0-9]+(-[a-z0-9]+)*', maxLength: 64, placeholder: title.toLowerCase().match(/[a-z0-9]+/g)?.slice(0, 8).join('-') || 'case' })), field(t('workflowKind'), h('select', { value: workflowKind, onChange: e => setWorkflowKind(e.target.value) }, ...['general', 'application-exploration', 'material-design'].map(value => h('option', { key: value, value }, t(value)))))), failure && h('div', { role: 'alert', className: 'hz-error' }, h('p', null, failureMessage), h('details', null, h('summary', null, t('failureDetails')), h('p', null, failure))), h('div', { className: 'hz-create-actions' }, h(Button, { type: 'button', variant: 'outline', disabled: busy, onClick: () => setCreating(false) }, t('cancel')), h(Button, { type: 'submit', variant: 'primary', disabled: busy || !ready || !selectedProject || !!loadError }, t('create')))));
    }
    function CaseMark({ sessionId, t }) {
      const state = useSyncExternalStore(subscribe, () => catalog);
      const c = state.projects.flatMap(p => p.cases).find(c => c.sessions.includes(sessionId));
      return h('span', { title: t(c ? 'cases' : 'discussion'), 'aria-label': t(c ? 'cases' : 'discussion'), className: 'hz-row-icon' }, c ? '▣' : '◯');
    }
    function CaseTrash({ sessionId, useMenuOpenState, t }) {
      const [, close] = useMenuOpenState(), state = useSyncExternalStore(subscribe, () => catalog);
      const p = state.projects.find(p => p.sessions.includes(sessionId)), c = p?.cases.find(c => c.sessions.includes(sessionId));
      if (!p) return null;
      return h(MenuItemButton, { icon: h(IconTrashOutlineRegular, { size: 14 }), onSelect: async () => { close(false); await api('archive.update', { projectId: p.id, id: c?.id || sessionId, kind: c ? 'case' : 'session', status: 'trash' }); await context.sessions.refresh(); publishCatalog(await api('state')); changed(); } }, t('trash'));
    }
    return { inject: ['slots', 'locale', 'remote', 'remote.session', 'uiWorkspace', 'sessions', 'workspaces', 'modelDirectories', 'sidebarRight', 'layout', 'documentPreviews'], apply(ctx) {
      context = ctx; ctx.locale.register('highzyme', { zh, en }); const t = ctx.locale.bind('highzyme');
      const register = (name, options, component) => ctx.slots.inject(name, () => ctx.slots.register({ name, locale: 'highzyme', ...options }, component));
      ctx.effect(() => ctx.documentPreviews.register({ id: 'highzyme-structure', extensions: ['cif', 'mmcif', 'pdb', 'mol', 'sdf', 'xyz', 'extxyz', 'vasp', 'poscar', 'contcar'], title: () => t('structureViewer'), loading: 'bytes-complete' }));
      register('sidebar.right.tab.document', { key: 'highzyme-structure' }, NativeStructurePreview);
      register('sidebar.brand.name', {}, () => h('strong', { className: 'hz-brand' }, 'mat-agent'));
      const MaterialMark = ({ size = 32 }) => h('span', { className: 'hz-material-mark', style: { width: size, height: size }, 'aria-hidden': true });
      register('sidebar.brand.mark', {}, MaterialMark);
      register('conversation.hero.brand.mark', {}, MaterialMark);
      register('sidebar.panellist', { id: 'highzyme', order: 5, label: () => t('hub') }, ({ size }) => h('svg', { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6 }, h('path', { d: 'M3 6h7l2 2h9v12H3zM3 6V4h7l2 2h9v2' })));
      register('main', { key: 'highzyme' }, ManagerLauncher);
      register('highzyme.resources', {}, ResourceManager);
      register('conversation.view', { id: 'highzyme-versions', order: 10, label: () => t('versions') }, VersionView);
      register('highzyme.file.grants', { id: 'highzyme-grants' }, FileGrant);
      register('highzyme.file.actions', { id: 'highzyme-file-actions' }, FileActions);
      register('sidebar.right.pane.tab.title', { key: '@deepseek-ai/dsh-client-ui-sidebar-files', priority: -10 }, ({ t }) => h('span', null, t('hub')));
      register('sidebar.session.row.leading', { id: 'highzyme-kind' }, CaseMark);
      register('sidebar.workspaces.session.menu.item', { id: 'highzyme-trash', order: 410 }, CaseTrash);
      register('shell.overlay', { id: 'highzyme-new' }, NewItemDialog);
      register('conversation.chat.assistant-actions', { id: 'highzyme-save', order: 30 }, ({ sessionId, messageId, t }) => button(t('saveAnswer'), () => launchResources(sessionId, 'artifacts', { sessionId, messageId })));
      for (const id of ['activity', 'usage']) register('conversation.composer.dock', { id, priority: -10 }, () => null);
      register('settings.section', { id: 'highzyme-access', order: 16, label: () => t('accessMenu'), children: { 'highzyme.settings.default-permission': { kind: 'list', scope: 'root' } } }, AccessSettings);
      register('highzyme.settings.default-model', {}, DefaultModel);
      register('settings.section', { id: 'highzyme-tools', order: 17, label: () => t('resources'), children: { 'plugins.item': { kind: 'list', scope: 'root' } } }, NativeTools);
      register('conversation.session.header.utilities', { id: 'highzyme-actions', order: -20 }, HeaderActions);
      // The product notices belong to the upstream service, not this local client.
      for (const id of ['welcome-notice', 'deepseek-official']) register('settings.onboarding', { id, priority: -10 }, ({ complete }) => { useEffect(() => { complete?.(); }, []); return null; });
      for (const id of ['developer-tools', 'performance-usage', 'current-version', 'shortcuts']) register('settings.general.item', { id, priority: -10 }, () => null);
      register('settings.action', { id: 'open-document', priority: -10 }, () => null);
      const observer = new MutationObserver(() => { if (document.title !== 'mat-agent') document.title = 'mat-agent'; });
      observer.observe(document.querySelector('title') || document.head, { childList: true, subtree: true }); ctx.effect(() => () => observer.disconnect());
    } };
  },
});
