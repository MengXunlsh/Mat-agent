"""Small extension seats over the pinned Harness bundle; native widgets stay intact."""
from pathlib import Path


def prepare_extensions(runtime: Path):
    from harness_lifecycle_extensions import prepare_lifecycle
    prepare_lifecycle(runtime)
    file = runtime / 'dsh-client-ui-deliverables/lib/client.js'
    source = file.read_text(encoding='utf-8')
    if '// Highzyme durable project versions' not in source:
        seat = 'const announced = showCodeDiff ? matched.changes : null;'
        if seat not in source:
            raise RuntimeError('Pinned Harness changed-file summary seat changed')
        source = source.replace(seat, 'const announced = null; // Highzyme durable project versions replace transient change cards.', 1)
        file.write_text(source, encoding='utf-8', newline='\n')
    file = runtime / 'dsh-api-session-controller/lib/index.js'
    source = file.read_text(encoding='utf-8')
    if '// Highzyme explicit default model' not in source:
        old = '''this.ctx.agentDefaultModel.saveSelection(selected).catch((error) => {
					this.ctx.logger.warn(`session-controller: model selection changed for the Session but the default was not saved: ${String(error)}`);
				});'''
        if old not in source:
            raise RuntimeError('Pinned Harness model-selection persistence changed')
        source = source.replace(old, '// Highzyme explicit default model: conversation selection stays local.', 1)
        source = source.replace('if (loggedHeader === void 0) return defaultModel.currentSelection();', 'if (loggedHeader === void 0 || !loggedHeader.config.provider || !loggedHeader.config.model) return defaultModel.currentSelection();', 1)
        file.write_text(source, encoding='utf-8', newline='\n')

    file = runtime / 'dsh-client-ui-model-selection/lib/client.js'
    source = file.read_text(encoding='utf-8')
    if 'exports.ModelSelect = ModelSelect;' not in source:
        source = source.replace('exports.ModelDirectory = ModelDirectory;', 'exports.ModelSelect = ModelSelect;\n\t\texports.ModelDirectory = ModelDirectory;', 1)
        file.write_text(source, encoding='utf-8', newline='\n')

    file = runtime / 'dsh-client-ui-settings-models/lib/client.js'
    source = file.read_text(encoding='utf-8')
    if 'highzyme.settings.default-model' not in source:
        seat = '(0, react_jsx_runtime.jsx)("ul", {\n\t\t\t\t\t\tclassName: ModelsSection_module_css_default["rows"],'
        source = source.replace(seat, 'renderSlot("highzyme.settings.default-model", {}),\n\t\t\t\t\t' + seat, 1)
        source = source.replace('"settings.models.footer": {', '"highzyme.settings.default-model": { kind: "single", scope: "root" },\n\t\t\t\t\t"settings.models.footer": {', 1)
        file.write_text(source, encoding='utf-8', newline='\n')

    file = runtime / 'dsh-client-ui-conversation/lib/client.js'
    source = file.read_text(encoding='utf-8')
    if '// Highzyme model admission' not in source:
        source = source.replace('submit(mode = "queue", source) {\n\t\t\t\tif (this.disposed) return;', '''submit(mode = "queue", source) {
				if (this.disposed) return;
                // Highzyme model admission preserves drafts and attachments.
                if (this.snapshot.phase === "plain" && !this.snapshot.draft.trim().startsWith("/") && (this.snapshot.draft.trim() || this.attachmentIds.length)) {
                    const model = this.deps.modelSelection?.();
                    if (model && (!model.current?.provider || !model.current?.model || model.routable === false)) {
                        this.notify("error", this.deps.modelRequiredNotice());
                        return;
                    }
                }''', 1)
        source = source.replace('const shell = new SessionInputShell({\n\t\t\t\t\tactx,', '''const shell = new SessionInputShell({
					actx,
                    modelSelection: () => this.rootCtx.get("modelDirectories")?.directoryFor(session.sessionId).store.getSnapshot(),
                    modelRequiredNotice: () => this.rootCtx.locale.bind("highzyme")("modelRequired"),''', 1)
        file.write_text(source, encoding='utf-8', newline='\n')
    file = runtime / 'dsh-client-ui-permission-presets/lib/client.js'
    source = file.read_text(encoding='utf-8')
    if 'highzyme.settings.default-permission' not in source:
        source = source.replace('"settings.general.item"', '"highzyme.settings.default-permission"')
        source = source.replace('"title": "权限"', '"title": "新会话默认权限"', 1).replace('"title": "Permission"', '"title": "New conversation default permissions"', 1)
        source = source.replace('const description = state.error ?? t("description");', 'const description = state.error;')
        source = source.replace('}), (0, react_jsx_runtime.jsx)("div", {\n\t\t\t\t\t\tclassName: PermissionRow_module_css_default.desc,', '}), description && (0, react_jsx_runtime.jsx)("div", {\n\t\t\t\t\t\tclassName: PermissionRow_module_css_default.desc,', 1)
        file.write_text(source, encoding='utf-8', newline='\n')

    file = runtime / 'dsh-client-ui-settings-web-search/lib/client.js'
    source = file.read_text(encoding='utf-8')
    if 'children: [t("useSearchApiHint")' in source:
        start = source.index('}), (0, react_jsx_runtime.jsxs)("p", {\n\t\t\t\t\t\t\tclassName: WebSearchCard_module_css_default.hint,')
        end = source.index('\n\t\t\t\t\t\t})]', start)
        source = source[:start] + '})]' + source[end + len('\n\t\t\t\t\t\t})]'):]
        file.write_text(source, encoding='utf-8', newline='\n')

    file = runtime / 'dsh-client-ui-chat/lib/client.js'
    source = file.read_text(encoding='utf-8')
    source = source.replace('const performanceUsage = performancePolicy.mode;', 'const performanceUsage = (0, _deepseek_ai_dsh_client_store.createSnapshotStore)("compact");')
    file.write_text(source, encoding='utf-8', newline='\n')

    sidebar = runtime / 'dsh-client-ui-sidebar/lib/client.js'
    content = sidebar.read_text(encoding='utf-8')
    if 'highzyme:new' not in content:
        pos = content.index('className: SidebarRoot_module_css_default.newSession,')
        content = content[:pos] + content[pos:].replace('startSession();', 'window.dispatchEvent(new Event("highzyme:new"));', 1)
        sidebar.write_text(content, encoding='utf-8', newline='\n')
    workspace = runtime / 'dsh-client-ui-workspace/lib/client.js'
    content = workspace.read_text(encoding='utf-8')
    if 'exports.recentWorkspace = recentWorkspace;' not in content:
        content = content.replace('exports.apply = apply;', 'exports.recentWorkspace = recentWorkspace;\n\t\texports.apply = apply;', 1)
        workspace.write_text(content, encoding='utf-8', newline='\n')
    if '// Highzyme missing project feedback' not in content:
        start = content.index('\t\t\t\tif (target === void 0) {', content.index('\t\t\tstartSession(workspaceId, options) {'))
        end = content.index('\n\t\t\t\t(draftOptions === void 0', start)
        content = content[:start] + '''\t\t\t\tif (target === void 0) {
                    // Highzyme missing project feedback
                    this.notify({ kind: "createFailed", message: this.ctx.locale.bind("workspace")("draft.workspaceRequired") });
                    return;
                }''' + content[end:]
        workspace.write_text(content, encoding='utf-8', newline='\n')
    trigger = 'window.dispatchEvent(new CustomEvent("highzyme:new", { detail: { projectId: group.workspaceId } }));'
    if trigger not in content:
        content = content.replace('startSession(group.workspaceId);', trigger, 1)
        workspace.write_text(content, encoding='utf-8', newline='\n')
    file = runtime / 'dsh-client-ui-sidebar-files/lib/client.js'
    source = file.read_text(encoding='utf-8')
    if '// Highzyme resource seats' not in source:
        source = source.replace('function FilesBody({', 'function NativeFilesBody({', 1)
        start = source.index('\t\tfunction NativeFilesBody(')
        source = source[:start] + '''\t\t// Highzyme resource seats
\t\tfunction FilesBody(props) {
\t\t\treturn props.renderSlot("highzyme.resources", { sessionId: props.sessionId, renderFiles: () => (0, react_jsx_runtime.jsx)(NativeFilesBody, props) });
\t\t}
''' + source[start:]
        source = source.replace('const tree = {\n\t\t\t\tstate,', 'const tree = {\n\t\t\t\tgrant: (file) => renderSlot("highzyme.file.grants", { absolutePath: file }),\n\t\t\t\tstate,', 1)
        source = source.replace('children: [expanded ? (0, react_jsx_runtime.jsx)', 'children: [tree.grant(path), expanded ? (0, react_jsx_runtime.jsx)', 1)
        source = source.replace('children: [(0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.FileTypeIcon, {', 'children: [tree.grant(path), (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.FileTypeIcon, {', 1)
        source = source.replace('children: { "sidebar.right.tab.files.actions": {', 'children: { "highzyme.resources": { kind: "single", scope: "session" }, "highzyme.file.grants": { kind: "list", scope: "session" }, "sidebar.right.tab.files.actions": {', 1)
        file.write_text(source, encoding='utf-8', newline='\n')

    if '// Highzyme checkbox siblings' not in source:
        source = source.replace('children: [tree.grant(path), expanded ?', 'children: [expanded ?', 1)
        source = source.replace('children: [tree.grant(path), (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.FileTypeIcon', 'children: [(0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.FileTypeIcon', 1)
        source = source.replace('"data-files-path": path,\n\t\t\t\t\tchildren: [(0, react_jsx_runtime.jsxs)("button",', '"data-files-path": path,\n\t\t\t\t\tchildren: [tree.grant(path), (0, react_jsx_runtime.jsxs)("button",', 1)
        source = source.replace('"data-files-path": path,\n\t\t\t\tchildren: (0, react_jsx_runtime.jsxs)("button",', '"data-files-path": path,\n\t\t\t\tchildren: [tree.grant(path), (0, react_jsx_runtime.jsxs)("button",', 1)
        source = source.replace('})\n\t\t\t});\n\t\t\treturn (0, react_jsx_runtime.jsx)("li",', '})]\n\t\t\t});\n\t\t\treturn (0, react_jsx_runtime.jsx)("li",', 1)
        source = source.replace('// Highzyme resource seats', '// Highzyme checkbox siblings\n\t\t// Highzyme resource seats', 1)
        file.write_text(source, encoding='utf-8', newline='\n')

    if '// Highzyme permission-only tree' not in source:
        source = source.replace('renderFiles: () => (0, react_jsx_runtime.jsx)(NativeFilesBody, props)', 'renderFiles: (options) => (0, react_jsx_runtime.jsx)(NativeFilesBody, { ...props, ...options })', 1)
        source = source.replace('function NativeFilesBody({ useTabInfo,', 'function NativeFilesBody({ permissionsOnly = false, useTabInfo,', 1)
        source = source.replace('grant: (file) => renderSlot("highzyme.file.grants", { absolutePath: file }),', 'permissionsOnly,\n\t\t\t\tgrant: (file) => permissionsOnly ? renderSlot("highzyme.file.grants", { absolutePath: file }) : null,', 1)
        leaf = source.index('if (entry.type === "file")')
        source = source[:leaf] + source[leaf:].replace('react_jsx_runtime.jsxs)("button",', 'react_jsx_runtime.jsxs)(tree.permissionsOnly ? "div" : "button",', 1)
        source = source.replace('tree.onOpen(path);', 'if (!tree.permissionsOnly) tree.onOpen(path);', 1)
        source = source.replace('renderSlot("sidebar.right.tab.files.actions", { absolutePath: state.root })', 'permissionsOnly ? null : renderSlot("sidebar.right.tab.files.actions", { absolutePath: state.root })', 1)
        source = source.replace('// Highzyme resource seats', '// Highzyme permission-only tree\n\t\t// Highzyme resource seats', 1)
        file.write_text(source, encoding='utf-8', newline='\n')

    if '// Highzyme unified refresh' not in source:
        source = source.replace('function NativeFilesBody({ permissionsOnly = false,', 'function NativeFilesBody({ refreshKey = 0, permissionsOnly = false,', 1)
        seat = 'const { tab } = useTabInfo();'
        source = source.replace(seat, seat + '\n\t\t\t(0, react.useEffect)(() => { if (refreshKey) refresh(tab.id); }, [refreshKey]);', 1)
        start = source.index('children: [(0, react_jsx_runtime.jsxs)("div", {\n\t\t\t\t\tclassName: FilesBody_module_css_default.header,')
        end = source.index('}), (0, react_jsx_runtime.jsx)("div", {\n\t\t\t\t\tref: bodyRef,', start)
        source = source[:start] + 'children: [(0, react_jsx_runtime.jsx)("div", {\n\t\t\t\t\tref: bodyRef,' + source[end + len('}), (0, react_jsx_runtime.jsx)("div", {\n\t\t\t\t\tref: bodyRef,'):]
        source = source.replace('// Highzyme resource seats', '// Highzyme unified refresh\n\t\t// Highzyme resource seats', 1)
        file.write_text(source, encoding='utf-8', newline='\n')

    file = runtime / 'dsh-client-ui-conversation/lib/client.js'
    source = file.read_text(encoding='utf-8')
    if 'data-highzyme-context' not in source:
        meter = '(0, react_jsx_runtime.jsx)(ContextMeter, {\n\t\t\t\t\t\t\tuseProjection,\n\t\t\t\t\t\t\tt\n\t\t\t\t\t\t})'
        if 'activity ? null : ' + meter not in source:
            raise RuntimeError('Pinned Harness context meter no longer matches')
        source = source.replace('activity ? null : ' + meter, 'null', 1)
        seat = 'sessionId === void 0 ? null : renderSlot("conversation.input.model", { locked: modelSeatLocked })'
        moved = '(0, react_jsx_runtime.jsx)("span", { "data-highzyme-context": true, children: (0, react_jsx_runtime.jsx)(ContextMeter, { useProjection, t }) }), ' + seat
        source = source.replace(seat, moved, 1)
        file.write_text(source, encoding='utf-8', newline='\n')

    file = runtime / 'dsh-api-session-controller/lib/index.js'
    source = file.read_text(encoding='utf-8')
    old = 'state.blank && event.type !== "turn/start"'
    new = old + ' && !(event.type === "session/title" && event.data.source?.kind === "user")'
    if new not in source:
        if old not in source:
            raise RuntimeError('Pinned Harness session metadata extension no longer matches')
        file.write_text(source.replace(old, new, 1), encoding='utf-8', newline='\n')

    file = runtime / 'dsh-client-ui-sidebar-files/lib/client.js'
    source = file.read_text(encoding='utf-8')
    if '// Highzyme persistent tree preferences' not in source:
        source = source.replace('function NativeFilesBody({ refreshKey = 0,', 'function NativeFilesBody({ initialView, onViewChange, refreshKey = 0,', 1)
        source = source.replace('const seeded = state !== void 0;', '''const seeded = state !== void 0;
            // Highzyme persistent tree preferences
            const viewRef = (0, react.useRef)(state);
            const restoredRef = (0, react.useRef)(false);
            const scrollTimer = (0, react.useRef)(null);
            if (state) viewRef.current = state;
            const saveView = () => {
                const view = viewRef.current;
                if (view) onViewChange?.({ root: view.root, expanded: view.expanded, scrollTop: restoredRef.current ? scrollTopRef.current : view.scrollTop });
            };
            (0, react.useLayoutEffect)(() => {
                if (!state || restoredRef.current || state.expanded.some(path => !state.levels[path] || state.levels[path].kind === "loading")) return;
                const body = bodyRef.current;
                if (body) { body.scrollTop = state.scrollTop; scrollTopRef.current = body.scrollTop; restoredRef.current = true; }
            }, [state?.levels]);
            (0, react.useEffect)(saveView, [state?.expanded, onViewChange]);''', 1)
        source = source.replace('if (seeded && !signal.aborted) actions.scrolled(tab.id, scrollTopRef.current);',
                                'clearTimeout(scrollTimer.current); saveView();\n                if (seeded && !signal.aborted) actions.scrolled(tab.id, scrollTopRef.current);', 1)
        source = source.replace('start(tab.id, cwd, signal);', 'start(tab.id, cwd, signal, initialView?.root === cwd ? initialView : undefined);', 1)
        source = source.replace('scrollTopRef.current = event.currentTarget.scrollTop;',
                                'scrollTopRef.current = event.currentTarget.scrollTop;\n                        clearTimeout(scrollTimer.current); scrollTimer.current = setTimeout(saveView, 200);', 1)
        source = source.replace('start(tabId, root, signal) {', 'start(tabId, root, signal, restore) {', 1)
        source = source.replace('actions.start(tabId, root);', 'actions.start(tabId, root, restore);', 1)
        start = source.index('start(tabId, root, signal, restore) {')
        end = source.index('load: (tabId', start)
        section = source[start:end].replace('}, signal).open());', '}, signal, restore?.expanded).open());', 1)
        source = source[:start] + section + source[end:]
        source = source.replace('start: (d, tabId, root) => {', 'start: (d, tabId, root, restore) => {', 1)
        source = source.replace('expanded: [root],\n\t\t\t\t\t\t\tscrollTop: 0,',
                                'expanded: restore?.expanded ?? [root],\n\t\t\t\t\t\t\tscrollTop: restore?.scrollTop ?? 0,', 1)
        file.write_text(source, encoding='utf-8', newline='\n')
