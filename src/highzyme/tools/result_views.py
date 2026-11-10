"""Read saved scientific outputs for the desktop result viewer; never rerun an analysis."""
import csv
import json
from pathlib import Path


def structure_view(raw, name):
    from highzyme.tools.nanozyme_structures import parse_nanozyme_structure
    if len(raw) > 32 * 1024**2:
        raise ValueError('Structure file exceeds 32 MiB')
    value = parse_nanozyme_structure(raw, name)
    value['atom_count'] = len(value['symbols'])
    if value.get('smiles'):
        value['depiction'] = molecule_svg(value['smiles'])
    return value


def molecule_svg(smiles):
    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D
    mol = Chem.MolFromSmiles(smiles)
    if mol is None or mol.GetNumAtoms() > 20000:
        raise ValueError('Invalid molecular graph')
    drawer = rdMolDraw2D.MolDraw2DSVG(600, 360)
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def export_identity(value, request):
    from highzyme.tools.analysis_outputs import export_analysis
    result = dict(value, schema='highzyme.identity.v1', title=value['formula'],
                  method=dict(name='Explicit chemical identity parsed by RDKit'),
                  summary={k: value[k] for k in ('formula', 'molar_mass_g_mol')})
    result['files'] = export_analysis(result, request)
    if value.get('smiles'):
        file = Path(request['output_prefix'] + '-structure.svg')
        file.write_text(molecule_svg(value['smiles']), encoding='utf-8')
        result['files']['depiction'] = str(file)
        with Path(result['files']['report']).open('a', encoding='utf-8') as stream:
            stream.write('\n![Molecular graph](' + file.name + ')\n')
    return result


def chart(ident, x_label, y_label, series, **options):
    return dict(id=ident, x_label=x_label, y_label=y_label, series=series, **options)


def kinetics_view(data, view):
    import numpy as np
    groups = data.get('groups') or [data]
    main, residuals, rows = [], [], []
    for i, group in enumerate(groups):
        label = group.get('label') or str(i + 1)
        x = group['concentration']; y = group['initial_rate']
        grid = np.linspace(min(x), max(x), 200)
        main.extend([dict(label=label, x=x, y=y, style='points', error=group.get('sigma'), color_index=i),
                     dict(label=label, x=grid.tolist(), y=(group['vmax'] * grid / (group['km'] + grid)).tolist(), color_index=i)])
        residuals.append(dict(label=label, x=x, y=group['residual'], style='points', color_index=i))
        se = group.get('standard_errors', {})
        rows.append(dict(group=label, km=group['km'], km_se=se.get('km'), concentration_unit=group['concentration_unit'],
                         vmax=group['vmax'], vmax_se=se.get('vmax'), rate_unit=group['rate_unit'],
                         r_squared=group['r_squared'], rmse=group['rmse'], n=group['n'], conditions=group.get('context', {})))
    first = groups[0]
    x_label = 'Substrate (' + first['concentration_unit'] + ')'
    view['charts'] = [chart('fit', x_label, 'Initial rate (' + first['rate_unit'] + ')', main),
                      chart('residuals', x_label, 'Residual (' + first['rate_unit'] + ')', residuals, zero_line=True)]
    view['tables'].append(dict(id='parameters', rows=rows))
    if len(groups) == 1:
        view['metrics'] = [dict(label='Km', value=first['km'], unit=first['concentration_unit'], se=rows[0]['km_se']),
                           dict(label='Vmax', value=first['vmax'], unit=first['rate_unit'], se=rows[0]['vmax_se']),
                           dict(label='R²', value=first['r_squared']), dict(label='n', value=first['n'])]
    view['conditions'] = data.get('assay_context')
    view['warnings'] = [warning for group in groups for warning in group.get('warnings', [])]


def qe_view(data, request, view):
    from highzyme.compute.qe_calculation import output_history
    output = request.get('files', {}).get('qe_out')
    history = data.get('history') or (output_history(Path(output).read_text(encoding='utf-8', errors='replace')) if output else {})
    iterations = history.get('iterations', [])
    for key, label in [('energy_Ry', 'Total energy (Ry)'), ('accuracy_Ry', 'Estimated SCF accuracy (Ry)')]:
        points = [(i + 1, row[key]) for i, row in enumerate(iterations) if row.get(key) is not None]
        if points:
            options = dict(y_scale='log') if key == 'accuracy_Ry' else {}
            if key == 'accuracy_Ry':
                options['threshold'] = data['request']['parameters'].get('electrons', {}).get('conv_thr', 1e-8)
            cycles = sorted({row['cycle'] for row in iterations})
            series = []
            for cycle in cycles:
                selected = [(i+1, row[key]) for i, row in enumerate(iterations) if row['cycle'] == cycle and row.get(key) is not None]
                if selected:
                    series.append(dict(label=label if len(cycles) == 1 else 'SCF ' + str(cycle), x=[p[0] for p in selected], y=[p[1] for p in selected]))
            view['charts'].append(chart('scf-' + key, 'Electronic iteration', label, series, **options))
    if history.get('ionic_steps') and data['request']['parameters'].get('calculation') == 'relax':
        view['tables'].append(dict(id='ionic-steps', rows=history['ionic_steps']))
    view['metrics'] = [dict(label='status', value=data['status']), dict(label='Energy', value=data.get('energy_Ry'), unit='Ry'),
                       dict(label='Formula', value=data['request']['structure']['formula']),
                       dict(label='SCF converged', value=data['scf_converged'])]
    view['parameters'] = data['request']['parameters']
    for role, label in [('structure', 'Input structure'), ('final_structure', 'Final structure')]:
        file = request.get('files', {}).get(role)
        if file:
            view['structures'].append(dict(label=label, **structure_view(Path(file).read_bytes(), Path(file).name)))


def evidence_view(data, view):
    materials = {m['id']: m for m in data['materials']}
    assays = {a['id']: a for a in data.get('assays', [])}
    rows = []
    for fact in data['facts']:
        material = materials[fact['material_id']]
        rows.append(dict(material=material['name'], version=material.get('version', ''),
                         assay=assays.get(fact.get('assay_id'), {}).get('label', ''), field=fact['field'],
                         value=fact['value_raw'], unit=fact.get('unit_raw', ''), review=fact['review'],
                         sources=fact['evidence']))
    view['tables'].append(dict(id='evidence', rows=rows))
    view['metrics'] = [dict(label=key, value=len(data.get(key, []))) for key in ('materials', 'assays', 'facts')]


def comparison_view(data, view):
    view['tables'].append(dict(id='comparison', rows=[dict(material=s['material'], version=s['version'], assay=s['assay'],
        **{field: '; '.join(f['value_raw'] + ' ' + f['unit_raw'] for f in facts) or None for field, facts in s['values'].items()}) for s in data['series']]))
    labels = {s['id']: s['material'] + ' / ' + s['assay'] for s in data['series']}
    for pair in data['pairs']:
        view['tables'].append(dict(id=labels[pair['left']] + ' ↔ ' + labels[pair['right']], rows=pair['fields']))


def calculation_view(data, request, view):
    kind = data['calculation']; values = data.get('data', {})
    view['metrics'] = [dict(label=key, value=value) for key, value in data.get('summary', {}).items()
                       if isinstance(value, (str, int, float, bool)) and key not in ('x_unit', 'y_unit', 'operation', 'hsv_scale')]
    if data.get('plot'):
        view['charts'].append(dict(id='curve', **data['plot']))
    if kind == 'signal':
        fit = values.get('calibration')
        if fit:
            x = [v for v in values['concentrations'] if v is not None]
            y = [v for v, good in zip(values['signal'], values['within_range']) if good]
            ends = fit['range']
            view['charts'].append(chart('calibration', 'Concentration (' + fit['x_unit'] + ')', 'Signal (' + fit['y_unit'] + ')',
                [dict(label='Calibration', x=ends, y=[fit['slope']*v + fit['intercept'] for v in ends]),
                 dict(label='Samples', x=x, y=y, style='points')]))
            view['metrics'].append(dict(label='Outside calibration range', value=len(values['within_range']) - sum(values['within_range'])))
            view['conditions'] = dict(calibration_range=fit['range'], unit=fit['x_unit'])
        if 'residuals' in values:
            view['charts'].append(chart('residuals', 'Concentration (' + values['x_unit'] + ')', 'Residual (' + values['y_unit'] + ')',
                [dict(label='Residuals', x=values['x'], y=values['residuals'], style='points')], zero_line=True))
        if 'range' in values:
            view['conditions'] = dict(calibration_range=values['range'], unit=values.get('x_unit'))
    if kind == 'formulation':
        view['tables'].append(dict(id='formulation', rows=[dict(parameter=key, value=value) for key, value in values.items()]))
    if kind == 'reaction':
        view['parameters'] = request.get('input', {}).get('parameters', {})
        parameters = view['parameters']
        def side(parts):
            return ' + '.join((str(count) + ' ' if count != 1 else '') + species for species, count in parts.items()) or '∅'
        view['reactions'] = [dict(equation=side(reaction['reactants']) + ' → ' + side(reaction['products']),
                                  k=reaction['k'], unit=values['rate_constant_units'][i], basis=reaction['parameter_basis']) for i, reaction in enumerate(parameters.get('reactions', []))]
        if parameters.get('curves'):
            view['tables'].append(dict(id='parameters', rows=parameters['curves']))
    if kind == 'colorimetry':
        view['image_records'] = values['images']


def result_view(request):
    files = request.get('files', {})
    data_file = files.get('result') or files.get('data')
    data = json.loads(Path(data_file).read_text(encoding='utf-8-sig')) if data_file else {}
    view = dict(kind='document', metrics=[], charts=[], tables=[], structures=[], images=[])
    first_group = (data.get('groups') or [{}])[0] if isinstance(data.get('groups'), list) else {}
    if data.get('schema') == 'highzyme.qe.workflow.result.v1':
        view.update(kind='qe-workflow', charts=data.get('charts', []), tables=data.get('tables', []), conditions=data.get('conditions'), parameters=data.get('parameters'), warnings=[data['error']] if data.get('error') else [])
        view['metrics'] = [dict(label='status', value=data['status']), dict(label='method', value=data['method'])]
        view['volume'] = data.get('volume')
        for record in data.get('structures', []):
            source = files.get('structure_' + record['label'])
            if source:
                value = structure_view(Path(source).read_bytes(), Path(source).name)
                value['label'] = record['label']
                view['structures'].append(value)
    elif data.get('schema') == 'highzyme.qe.result.v1':
        view['kind'] = 'qe'; qe_view(data, request, view)
    elif data.get('model') == 'v = Vmax * S / (Km + S)' or isinstance(first_group, dict) and first_group.get('model') == 'v = Vmax * S / (Km + S)':
        view['kind'] = 'kinetics'; kinetics_view(data, view)
    elif data.get('schema') == 'highzyme.calculation.v1':
        view['kind'] = data['calculation']; calculation_view(data, request, view)
    elif data.get('schema') == 'highzyme.case.research.v1':
        view['kind'] = 'research'
        names = {'general': '通用研究', 'application-exploration': '应用方向探索', 'material-design': '材料候选设计'} if data.get('language') != 'en' else {}
        view['metrics'] = [dict(label='workflowKind', value=names.get(data['kind'], data['kind'].replace('-', ' '))), dict(label='candidates', value=len(data['candidates']))]
        view['tables'].append(dict(id='candidates', columns=['title', 'hypothesis', 'baseline', 'state', 'validationOutcome'], rows=[
            dict(title=c['title'], hypothesis=c['hypothesis'], baseline=c['baseline'], state=c['status'], validationOutcome=c.get('validation_outcome', 'not_validated')) for c in data['candidates']]))
    elif data.get('schema') == 'highzyme.dataset-record.v1':
        view['kind'] = 'dataset'
        selection = data['selection']
        view['metrics'] = [dict(label='material', value=selection['material_name']),
                           dict(label='observations', value=len(data['observations']))]
        view['tables'].append(dict(id='observations', columns=['field', 'value', 'unit', 'origin'], rows=[
            dict(field=o['field'].split('.')[-1].replace('_', ' '), value=o.get('value'),
                 unit=o.get('unit', ''), origin=' · '.join(o.get('source', []))) for o in data['observations']]))
    elif data.get('schema') == 'highzyme.evidence.v1':
        view['kind'] = 'evidence'; evidence_view(data, view)
    elif data.get('pairs') and data.get('series'):
        view['kind'] = 'comparison'; comparison_view(data, view)
    elif data.get('formula') or data.get('element_counts') or data.get('smiles'):
        view['kind'] = 'identity'
        view['metrics'] = [dict(label=label, value=data[key], unit=unit) for key, label, unit in
                           [('formula', 'Formula', ''), ('molar_mass_g_mol', 'Molar mass', 'g/mol'),
                            ('formal_charge', 'Formal charge', ''), ('component_count', 'Components', '')] if key in data]
        if data.get('smiles'):
            view['depiction'] = molecule_svg(data['smiles'])
        if data.get('element_counts'):
            view['tables'].append(dict(id='composition', rows=[dict(element=k, count=v, mass_fraction=data.get('element_mass_fractions', {}).get(k)) for k, v in data['element_counts'].items()]))
    table = files.get('table')
    if table and view['kind'] not in ('evidence', 'comparison'):
        with Path(table).open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        if rows:
            view['tables'].append(dict(id='measurements', rows=rows, **(dict(columns=['file', 'region', 'pixels', 'mean_r', 'mean_g', 'mean_b', 'mean_h', 'mean_s', 'mean_v']) if view['kind'] == 'colorimetry' else {})))
    structure = files.get('structure')
    if structure and not view['structures']:
        view['structures'].append(structure_view(Path(structure).read_bytes(), Path(structure).name))
    if files.get('options'):
        options = json.loads(Path(files['options']).read_text(encoding='utf-8-sig'))
        view['saved_layout'] = options.get('layout')
        for plot in view['charts']:
            if plot['id'] in ('fit', 'curve'):
                for key in ('x_label', 'y_label'):
                    if options.get(key):
                        plot[key] = options[key]
                if options.get('labels'):
                    labels = options['labels']
                    for i, item in enumerate(plot['series']):
                        item['label'] = labels[i // 2] if view['kind'] == 'kinetics' else labels[i]
    from highzyme.tools.figure_style import COLORS
    for plot in view['charts']:
        plot['palette'] = list(COLORS)
    return view
