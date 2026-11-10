"""Project evidence records, source checks and purpose-specific comparisons."""
from copy import deepcopy
import csv
import hashlib
import itertools
import json
from pathlib import Path
import re
from pint.errors import PintError

from highzyme.evidence.local_documents import _docx_blocks, MAX_DOCUMENT_BYTES
from highzyme.tools.assay import QUANTITY_FIELDS, compare_field

SCHEMA = 'highzyme.evidence.v1'


def load_json(file):
    path = Path(file)
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError('Evidence file exceeds 32 MiB')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def table_cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def source_excerpt(file, locator, cache):
    if file not in cache:
        path = Path(file)
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise ValueError('Source exceeds 32 MiB')
        suffix = path.suffix.lower()
        if suffix == '.pdf':
            from pypdf import PdfReader
            content = PdfReader(path)
        elif suffix == '.docx':
            content = {r['locator']: r['text'] for r in _docx_blocks(path)}
        elif suffix in ('.md', '.txt'):
            content = path.read_text(encoding='utf-8-sig').splitlines()
        else:
            raise ValueError('Evidence sources support PDF, DOCX, Markdown and TXT')
        cache[file] = (suffix, content, hashlib.sha256(path.read_bytes()).hexdigest())
    suffix, content, digest = cache[file]
    if suffix == '.pdf':
        match = re.fullmatch(r'PDF/page\[(\d+)\]', locator)
        if not match or not 1 <= int(match[1]) <= len(content.pages):
            raise ValueError('Use an existing PDF/page[n] locator')
        page_key = (file, locator)
        if page_key not in cache:
            cache[page_key] = content.pages[int(match[1])-1].extract_text() or ''
        text = cache[page_key]
    elif suffix == '.docx':
        if locator not in content:
            raise ValueError('DOCX locator does not exist: ' + locator)
        text = content[locator]
    else:
        match = re.fullmatch(r'lines\[(\d+)(?::(\d+))?\]', locator)
        if not match or not 1 <= int(match[1]) <= int(match[2] or match[1]) <= len(content):
            raise ValueError('Use an existing lines[start:end] locator')
        text = '\n'.join(content[int(match[1])-1:int(match[2] or match[1])])
    return text, digest


def validate_dataset(dataset, root=None):
    data = deepcopy(dataset)
    if not isinstance(data, dict) or data.get('schema') != SCHEMA:
        raise ValueError('Expected schema ' + SCHEMA)
    maps = {}
    for key in ('materials', 'assays', 'facts'):
        rows = data.get(key)
        if not isinstance(rows, list) or not rows or len(rows) > 300 or any(not isinstance(r, dict) for r in rows):
            raise ValueError('Supply at most 300 ' + key)
        ids = [r.get('id') for r in rows]
        if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('Each ' + key + ' row needs a unique nonempty id')
        maps[key] = {r['id']: r for r in rows}
    for material in data['materials']:
        if not isinstance(material.get('name'), str) or not material['name'].strip():
            raise ValueError('Each material needs a name')
    for assay in data['assays']:
        if assay.get('material_id') not in maps['materials'] or not assay.get('label'):
            raise ValueError('Each assay needs a label and a known material_id')
    cache = {}
    for fact in data['facts']:
        if fact.get('material_id') not in maps['materials']:
            raise ValueError('Unknown material_id in fact ' + fact['id'])
        if fact.get('assay_id'):
            assay = maps['assays'].get(fact['assay_id'])
            if not assay or assay['material_id'] != fact['material_id']:
                raise ValueError('Fact and assay must refer to the same material: ' + fact['id'])
        if not isinstance(fact.get('field'), str) or not fact['field'].strip() or not isinstance(fact.get('value_raw'), str):
            raise ValueError('Facts need a field and verbatim string value_raw')
        if fact.get('review', 'needs_review') not in ('supported', 'needs_review', 'conflict'):
            raise ValueError('Unknown fact review state')
        fact.setdefault('review', 'needs_review')
        fact.setdefault('unit_raw', '')
        if not isinstance(fact['unit_raw'], str):
            raise ValueError('unit_raw must be a string')
        evidence = fact.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            raise ValueError('Each fact needs source evidence')
        for ref in evidence:
            if not isinstance(ref, dict) or any(not isinstance(ref.get(k), str) or not ref[k].strip() for k in ('file', 'locator', 'quote')):
                raise ValueError('Evidence requires file, locator and quote strings')
            if root is None:
                continue
            text, digest = source_excerpt(str(Path(root) / ref['file']), ref['locator'], cache)
            if ref.get('source_sha256') and ref['source_sha256'] != digest:
                raise ValueError('Source changed; read it again: ' + ref['file'])
            basis = ref.get('basis', 'text')
            if basis not in ('text', 'visual'):
                raise ValueError('Evidence basis must be text or visual')
            if basis == 'text':
                quote = ref.get('quote')
                if not isinstance(quote, str) or not quote.strip() or ' '.join(quote.split()) not in ' '.join(text.split()):
                    raise ValueError('Evidence quote was not found at its locator: ' + fact['id'])
            ref.update(source_sha256=digest, check='text_match' if basis == 'text' else 'source_located_visual_not_checked')
    if root is not None:
        data['source_check'] = 'Source positions and text matches checked; fact interpretation retains its declared review state.'
    return data


def save_evidence(request):
    data = validate_dataset(load_json(request['file']), request['root'])
    prefix = Path(request['output_prefix'])
    files = {key: prefix.with_name(prefix.name + suffix) for key, suffix in {'data': '-evidence.json', 'table': '-evidence.csv', 'report': '-report.md'}.items()}
    prefix.parent.mkdir(parents=True, exist_ok=True)
    files['data'].write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    fields = ['id', 'material_id', 'assay_id', 'field', 'value_raw', 'unit_raw', 'review', 'evidence']
    with files['table'].open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for fact in data['facts']:
            writer.writerow({k: json.dumps(fact[k], ensure_ascii=False) if k == 'evidence' else fact.get(k, '') for k in fields})
    zh = request.get('language') == 'zh'
    materials = {m['id']: m for m in data['materials']}
    assays = {a['id']: a for a in data['assays']}
    report = ['# ' + data.get('title', 'Literature evidence'), '', data.get('question', ''), '',
              '| 材料 / 版本 | 测定 | 字段 | 原文值 | 单位 | 核查状态 | 来源 |' if zh else '| Material / version | Assay | Field | Raw value | Unit | Review | Source |',
              '|---|---|---|---|---|---|---|']
    for fact in data['facts']:
        material = materials[fact['material_id']]
        row = [material['name'] + (' / ' + material['version'] if material.get('version') else ''),
               assays.get(fact.get('assay_id'), {}).get('label', ''), fact['field'], fact['value_raw'], fact['unit_raw'], fact['review'],
               '; '.join(ref['file'] + ' ' + ref['locator'] for ref in fact['evidence'])]
        report.append('| ' + ' | '.join(map(table_cell, row)) + ' |')
    report += ['', '文件位置与文本引文已核对；字段含义和样品归属的判断保留在核查状态中。' if zh else data['source_check']]
    files['report'].write_text('\n'.join(report) + '\n', encoding='utf-8')
    return {'counts': {key: len(data[key]) for key in ('materials', 'assays', 'facts')}, 'files': {k: str(v) for k, v in files.items()}}


def compare_evidence(request):
    purpose = request.get('purpose', 'overview')
    if purpose not in ('overview', 'material_activity', 'condition_effect'):
        raise ValueError('Choose overview, material_activity or condition_effect')
    fields = request.get('fields') or ['activity', 'substrate', 'pH', 'temperature', 'material_dose', 'km', 'vmax']
    if not isinstance(fields, list) or not 1 <= len(fields) <= 30 or any(not isinstance(f, str) or not f.strip() for f in fields) or len(set(fields)) != len(fields):
        raise ValueError('Choose 1 to 30 distinct field names')
    varied = request.get('varied_field')
    aliases = {'ph': 'pH', 'vmax': 'vmax', 'km': 'km', 'catalyst_concentration': 'material_dose',
               'enzyme_mimic_type': 'activity', 'activity_type': 'activity'}
    canonical = lambda field: aliases.get(field.rsplit('.', 1)[-1].casefold(), field)
    fields = list(dict.fromkeys(canonical(field) for field in fields))
    varied = canonical(varied) if varied else varied
    if purpose == 'condition_effect' and varied not in fields:
        raise ValueError('Select the intended varied_field among the compared fields')
    series = []
    for selection in request['selections']:
        data = load_json(selection['file'])
        if data.get('schema') == 'highzyme.dataset-record.v1':
            from highzyme.evidence.dataset_evidence import comparison_evidence
            data = comparison_evidence(data, selection.get('source_label', selection['file']))
        data = validate_dataset(data)
        materials = {m['id']: m for m in data['materials']}
        assays = {a['id']: a for a in data['assays']}
        for ident in selection['assay_ids']:
            if ident not in assays:
                raise ValueError('Unknown assay: ' + ident)
            assay = assays[ident]; material = materials[assay['material_id']]
            row = {'id': selection.get('source_label', selection['file']) + '#' + ident,
                   'material': material['name'], 'version': material.get('version', ''), 'assay': assay['label'], 'dataset_sha256': hashlib.sha256(Path(selection['file']).read_bytes()).hexdigest(), 'coverage': data.get('coverage', {}), 'values': {}}
            for field in fields:
                facts = [f for f in data['facts'] if f.get('assay_id') == ident and canonical(f['field']) == field]
                row['values'][field] = [{'value_raw': f['value_raw'], 'unit_raw': f.get('unit_raw', ''), 'review': f.get('review', 'needs_review'), 'fact_id': f['id'], 'evidence': f['evidence'], **({'kinetic_context': f['kinetic_context']} if 'kinetic_context' in f else {})} for f in facts]
            series.append(row)
    if not 2 <= len(series) <= 12 or len({s['id'] for s in series}) != len(series):
        raise ValueError('Choose 2 to 12 distinct assays')
    pairs = []
    for left, right in itertools.combinations(series, 2):
        rows = []
        for field in fields:
            a, b = left['values'][field], right['values'][field]
            incomplete = any(not row['values'][field] and row['coverage'].get('truncated') for row in (left, right))
            state = 'not_read' if incomplete else 'missing' if not a or not b else 'multiple_values' if len(a) != 1 or len(b) != 1 else 'unreviewed' if any(x[0]['review'] != 'supported' for x in (a, b)) else None
            if state is None and field in ('km', 'vmax') and any('kinetic_context' in x[0] for x in (a, b)):
                key = 'substrate' if field == 'km' else 'normalization_basis'
                contexts = [x[0].get('kinetic_context', {}).get(key) for x in (a, b)]
                if not all(contexts) or str(contexts[0]).strip().casefold() != str(contexts[1]).strip().casefold():
                    state = 'needs_interpretation'
            if state is None:
                try:
                    if field in QUANTITY_FIELDS or field in ('km', 'vmax'):
                        va, vb = ({'value': float(x[0]['value_raw']), 'unit': x[0]['unit_raw']} for x in (a, b))
                    elif field == 'pH':
                        va, vb = (float(x[0]['value_raw']) for x in (a, b))
                    else:
                        va, vb = (x[0]['value_raw'] + (' ' + x[0]['unit_raw'] if x[0]['unit_raw'] else '') for x in (a, b))
                    equal, comparable = compare_field(field, va, vb)
                    state = 'matched' if equal else 'different' if comparable else 'unit_mismatch'
                except (ValueError, TypeError, PintError):
                    state = 'needs_interpretation'
            rows.append({'field': field, 'state': state, 'role': 'result' if field in ('km', 'vmax') else 'intended_variable' if field == varied else 'context'})
        pairs.append({'left': left['id'], 'right': right['id'], 'fields': rows,
                      'different_material': (left['material'], left['version']) != (right['material'], right['version'])})
    result = {'purpose': purpose, 'question': request.get('question', ''), 'fields': fields, 'series': series, 'pairs': pairs}
    prefix = Path(request['output_prefix']); prefix.parent.mkdir(parents=True, exist_ok=True)
    files = {key: prefix.with_name(prefix.name + suffix) for key, suffix in {'data': '-comparison.json', 'table': '-comparison.csv', 'report': '-report.md'}.items()}
    files['data'].write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with files['table'].open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(['assay', 'material', 'version', 'field', 'value_raw', 'unit_raw', 'review', 'fact_id', 'kinetic_substrate', 'normalization_basis'])
        for row in series:
            for field, facts in row['values'].items():
                for fact in facts or [{'value_raw': '', 'unit_raw': '', 'review': 'not_read' if row['coverage'].get('truncated') else 'missing', 'fact_id': ''}]:
                    context = fact.get('kinetic_context', {})
                    writer.writerow([row['id'], row['material'], row['version'], field, fact['value_raw'], fact['unit_raw'], fact['review'], fact['fact_id'], context.get('substrate', ''), context.get('normalization_basis', '')])
    zh = request.get('language') == 'zh'
    report = ['# ' + ('材料与测定条件比较' if zh else 'Material and assay comparison'), '', result['question'], '',
              '| 测定 / 材料 | ' + ' | '.join(map(table_cell, fields)) + ' |' if zh else '| Assay / material | ' + ' | '.join(map(table_cell, fields)) + ' |',
              '|---|' + '---|' * len(fields)]
    for row in series:
        missing = ('读取不完整' if zh else 'Incomplete read') if row['coverage'].get('truncated') else ('缺失' if zh else 'Missing')
        values = ['; '.join(f['value_raw'] + ' ' + f['unit_raw'] for f in row['values'][field]) or missing for field in fields]
        report.append('| ' + ' | '.join(map(table_cell, [row['id'] + ' / ' + row['material'] + ' ' + row['version'], *values])) + ' |')
    labels = {'not_read': '读取不完整', 'missing': '缺失', 'multiple_values': '多个值待核对', 'unreviewed': '尚未核查或有冲突', 'matched': '一致', 'different': '不同', 'unit_mismatch': '单位基准不一致', 'needs_interpretation': '需核对数值、单位或测定基准'}
    for pair in pairs:
        report += ['', '## ' + pair['left'] + ' — ' + pair['right']]
        if purpose == 'condition_effect' and pair['different_material']:
            report.append('材料或版本也不同，需要同时考虑。' if zh else 'Material or version also differs and must be considered.')
        report += ['- ' + r['field'] + ': ' + (labels[r['state']] if zh else r['state']) + (' (' + ({'result': '结果', 'intended_variable': '目标变量'}[r['role']] if zh else r['role']) + ')' if r['role'] != 'context' else '') for r in pair['fields']]
    files['report'].write_text('\n'.join(report) + '\n', encoding='utf-8')
    return {'series_count': len(series), 'pairs': pairs, 'files': {k: str(v) for k, v in files.items()}}
