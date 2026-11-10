"""Reproducible product copy and UI extension hooks for the pinned Web bundle.

The rules below are the source; installed JS is regenerated, never hand edited.
Protocol identifiers, tool names and third-party attribution remain intact.
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'integrations/deepseek-harness/web-runtime/node_modules/@deepseek-ai'

COPY = {
    '探索未至之境': '开始你的研究',
    'Into the Unknown': 'Start your research',
    '深度求索中': '思考中',
    '深度求索中，用时 {duration} ···': '思考中，用时 {duration} ···',
    'Deep diving': 'Thinking',
    'Deep diving for {duration} ···': 'Thinking for {duration} ···',
    '描述你想要构建的内容, / 调用指令, @ 文件或对话': '描述研究任务，/ 调用指令，@ 引用文件或会话',
    'No key is configured; only conversations using a DeepSeek Account model can search, through the default endpoint.': 'Configure your own search API key. Search and chat model connections are independent.',
    '未配置密钥；仅使用 DeepSeek 账号模型的对话可以通过默认接口地址搜索。': '请配置你自己的检索 API 密钥；检索服务与聊天模型分别配置。',
}


def prepare_product_copy():
    if __package__:
        from .harness_ui_extensions import prepare_extensions
    else:
        from harness_ui_extensions import prepare_extensions
    prepare_extensions(RUNTIME)
    preview = RUNTIME / 'dsh-client-ui-sidebar-documentpreview/lib/client.js'
    source = preview.read_text(encoding='utf-8')
    suffix_match = 'name.endsWith(`.${extension}`)'
    if 'Highzyme extensionless structures' not in source:
        if suffix_match not in source:
            raise RuntimeError('The pinned document-preview suffix matcher changed')
        source = source.replace(suffix_match, '(name.endsWith(`.${extension}`) || /* Highzyme extensionless structures */ ["poscar", "contcar"].includes(extension) && name === extension)', 1)
        preview.write_text(source, encoding='utf-8', newline='\n')
    packages = ['dsh-client-locale', 'dsh-client-ui-sidebar', 'dsh-client-ui-workspace', 'dsh-client-ui-conversation', 'dsh-client-ui-chat', 'dsh-client-ui-directory-picker-browse', 'dsh-client-ui-directory-picker-native', 'dsh-client-ui-permission-presets', 'dsh-client-ui-settings-web-search', 'dsh-client-ui-sidebar-files', 'dsh-client-ui-sidebar-terminal']
    changes = []
    for package in packages:
        file = RUNTIME / package / 'lib/client.js'
        if not file.exists():
            continue
        original = file.read_text(encoding='utf-8')
        # Limit replacements to the locale source region; internal workspace
        # protocol identifiers and third-party attribution remain untouched.
        def region(match):
            def string_value(item):
                prefix, literal = item.groups()
                value = json.loads(literal)
                value = COPY.get(value, value)
                if package == 'dsh-client-ui-sidebar' and '"session.new' in prefix:
                    value = '新建' if not value.isascii() else 'New'
                if 'hero.preview' in prefix:
                    value = ''
                if 'placeholder.hero' in prefix and value.isascii():
                    value = 'Describe your research task, / for commands, @ for files or conversations'
                value = value.replace('工作区', '项目')
                value = re.sub(r'\bWorkspaces\b', 'Projects', value)
                value = re.sub(r'\bWorkspace\b', 'Project', value)
                value = re.sub(r'\bworkspaces\b', 'projects', value)
                value = re.sub(r'\bworkspace\b', 'project', value)
                return prefix + json.dumps(value, ensure_ascii=False)
            return re.sub(r'((?:"[^"\n]+"|\b\w+)\s*:\s*)("(?:[^"\\]|\\.)*")', string_value, match.group(0))
        updated = re.sub(r'//\#region [^\n]*locales?(?:/[^\n]+)?\.js\n[\s\S]*?//\#endregion', region, original)
        if updated != original:
            file.write_text(updated, encoding='utf-8', newline='\n')
            changes.append(package)
    file = RUNTIME / 'dsh-client-ui-agent-preset/lib/client.js'
    source = file.read_text(encoding='utf-8')
    if '// Highzyme research preset' not in source:
        source = source.replace('function presetDisplayText(preset, t) {', 'function presetDisplayText(preset, t) {\n\t\t\t// Highzyme research preset\n\t\t\tif (preset.id === "research") return { name: t("researchName"), description: t("researchDescription") };', 1)
        source = source.replace('const en = {\n', 'const en = {\n\t\t\tresearchName: "General research", researchDescription: "Literature, data, structures, code and research documents.",\n', 1)
        source = source.replace('const zh = {\n', 'const zh = {\n\t\t\tresearchName: "通用研究", researchDescription: "文献、数据、结构、代码与研究文档。",\n', 1)
        source = source.replace('if (!main) return null;\n\t\t\tconst characters = Array.from(label);', 'if (!main) return null;\n\t\t\tif (ready && options.length === 1) return (0, react_jsx_runtime.jsx)("span", { className: AgentPresetLabel_module_css_default.label, children: label });\n\t\t\tconst characters = Array.from(label);', 1)
        file.write_text(source, encoding='utf-8', newline='\n')
        changes.append('dsh-client-ui-agent-preset')
    updated = re.sub(r'\t*ctx\.slots\.inject\("settings\.section", \(\) => ctx\.slots\.register\(\{\s*name: "settings\.section",\s*id: "agent-presets",[\s\S]*?\}, AgentPresetSection\)\);', '', source, count=1)
    if updated != source:
        file.write_text(updated, encoding='utf-8', newline='\n')
        changes.append('highzyme-single-mode-settings')
    file = RUNTIME / 'dsh-client-ui-sidebar-files/lib/client.js'
    source = file.read_text(encoding='utf-8')
    updated = source.replace('grant: (file) => permissionsOnly ? renderSlot("highzyme.file.grants", { absolutePath: file }) : null,', 'grant: (file) => permissionsOnly ? renderSlot("highzyme.file.grants", { absolutePath: file }) : renderSlot("highzyme.file.actions", { absolutePath: file, sessionId }),')
    if '"highzyme.file.actions": {' not in updated:
        updated = updated.replace('"highzyme.file.grants": { kind: "list", scope: "session" },', '"highzyme.file.grants": { kind: "list", scope: "session" }, "highzyme.file.actions": { kind: "list", scope: "session" },', 1)
    if updated != source:
        file.write_text(updated, encoding='utf-8', newline='\n')
        changes.append('highzyme-file-actions')
    file = RUNTIME / 'dsh-client-ui-skill/lib/client.js'
    source = file.read_text(encoding='utf-8')
    descriptions = {
            'literature-evidence': ('文献阅读与证据抽取：保留材料、测定条件及原文位置。', 'Read literature and extract source-linked evidence.'),
            'assay-comparison': ('比较材料、测定条件和结果，保留来源与缺失项。', 'Compare source-linked materials, assay conditions and results.'),
            'material-structure-check': ('核对化学式、分子与晶体结构文件。', 'Check chemical identity and molecular or crystal structure files.'),
            'initial-rate-kinetics': ('拟合底物浓度—初始速率，保存参数、图件和复跑脚本。', 'Fit substrate concentration versus initial rate with reproducible outputs.'),
            'discussion-artifact': ('将选定讨论整理为笔记、方案或结果报告。', 'Organize selected discussion into notes, plans or reports.'),
            'formulation-calculations': ('计算配液、稀释、用量、比例及单位换算。', 'Calculate recipes, dilutions, quantities, ratios and units.'),
            'signal-analysis': ('分析标定、信号和荧光校正数据。', 'Analyze calibration, readout and fluorescence correction data.'),
            'image-colorimetry': ('读取图像选区的 RGB/HSV，保存取样图和数据。', 'Measure image ROI RGB/HSV and save annotated sampling images.'),
            'reaction-simulation': ('模拟给定动力学参数或反应网络。', 'Simulate declared kinetic parameters or reaction networks.'),
            'publication-retrieval': ('获取指定论文及公开补充材料。', 'Retrieve an identified publication and public supporting information.'),
            'scientific-plotting': ('按统一科研样式绘图或调整现有图件。', 'Plot research data or restyle figures with the shared scientific profile.'),
    }
    if '// Highzyme skill labels' not in source:
        for locale, index in [('zh', 0), ('en', 1)]:
            entries = ',\n'.join(json.dumps('highzyme.' + key) + ': ' + json.dumps(value[index], ensure_ascii=False) for key, value in descriptions.items())
            source = source.replace('const ' + locale + ' = {', 'const ' + locale + ' = {\n' + entries + ',', 1)
        source = source.replace('description: skill.modelInvocable ? skill.description : `${t("menu.userOnly")} · ${skill.description}`',
            '// Highzyme skill labels\n\t\t\t\t\t\tdescription: ' + json.dumps(list(descriptions)) + '.includes(skill.name) ? t("highzyme." + skill.name) : skill.modelInvocable ? skill.description : `${t("menu.userOnly")} · ${skill.description}`', 1)
        file.write_text(source, encoding='utf-8', newline='\n')
        changes.append('highzyme-skill-labels')
    previous = source
    for key, values in descriptions.items():
        if '"highzyme.' + key + '"' not in source:
            for locale, index in [('zh', 0), ('en', 1)]:
                source = source.replace('const ' + locale + ' = {', 'const ' + locale + ' = {\n' + json.dumps('highzyme.' + key) + ': ' + json.dumps(values[index], ensure_ascii=False) + ',', 1)
    source = re.sub(r'(description: )\[[^\]]*\](\.includes\(skill\.name\))', lambda m: m[1] + json.dumps(list(descriptions)) + m[2], source)
    if source != previous:
        file.write_text(source, encoding='utf-8', newline='\n')
        changes.append('highzyme-research-skill-labels')
    return changes


if __name__ == '__main__':
    print(json.dumps({'product_copy': prepare_product_copy()}, ensure_ascii=False))
