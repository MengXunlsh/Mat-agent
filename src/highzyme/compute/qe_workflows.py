"""Composable, file-based scientific workflows using ASE and Quantum ESPRESSO."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import re
import sys

import numpy as np
from ase.io import read, write
from ase.io.espresso import write_fortran_namelist
from ase.units import Rydberg

from highzyme.compute.connector import child_path
from highzyme.compute.qe_calculation import prepare as prepare_pw, sha256


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', value):
        raise ValueError('Use lowercase English keywords separated by hyphens for model and stage IDs')
    return value


def post_input(file, sections):
    with Path(file).open('w', encoding='utf-8', newline='\n') as stream:
        write_fortran_namelist(stream, input_data=sections)


class Workflow:
    def __init__(self, request):
        self.root, self.folder = Path(request['root']), Path(request['directory'])
        self.config = deepcopy(request['config'])
        self.folder.mkdir(parents=True, exist_ok=True)
        self.programs = {'pw': 'pw.x', 'dos': 'dos.x', 'projwfc': 'projwfc.x', 'bands': 'bands.x', 'pp': 'pp.x', 'neb': 'neb.x', 'bader': 'bader', **request.get('programs', {})}
        self.stages, self.models, self.atoms, self.records = [], {}, {}, {}
        for model in self.config['models']:
            name = identifier(model['id'])
            if name in self.models:
                raise ValueError('Duplicate model ID: ' + name)
            self.models[name] = model
            self.atoms[name] = read(child_path(self.root, model['structure_file']))
        self.pseudos = {s: str(child_path(self.root, file)) for s, file in self.config['pseudopotentials'].items()}

    def pw(self, stage_id, model_id, parameters=None, atoms=None, shared=None):
        stage_id = identifier(stage_id)
        model = self.models[model_id]
        settings = deepcopy(self.config['parameters'])
        for key, value in model.get('parameters', {}).items():
            settings[key] = {**settings.get(key, {}), **value} if isinstance(value, dict) else value
        for key, value in (parameters or {}).items():
            settings[key] = {**settings.get(key, {}), **value} if isinstance(value, dict) else value
        settings.setdefault('calculation', 'scf')
        settings['control'] = {**settings.get('control', {}), 'tprnfor': True}
        structure = child_path(self.root, model['structure_file'])
        if atoms is not None:
            structure = self.folder / 'structures' / (stage_id + '.extxyz')
            structure.parent.mkdir(exist_ok=True)
            write(structure, atoms)
        folder = self.folder / stage_id
        result = prepare_pw({'directory': str(folder), 'structure_file': str(structure), 'parameters': settings,
                             'scratch_dir': '../shared/' + identifier(shared or stage_id),
                             'pseudopotentials': {s: self.pseudos[s] for s in set((atoms if atoms is not None else self.atoms[model_id]).get_chemical_symbols())}})
        self.records[stage_id] = result['request']
        self.stages.append(dict(id=stage_id, model=model_id, program='pw', folder=stage_id, input='qe.in', output='qe.out', calculation=settings['calculation']))
        return stage_id

    def post(self, stage_id, model_id, program, sections, outputs, arguments=None):
        stage_id = identifier(stage_id)
        folder = self.folder / stage_id
        folder.mkdir(exist_ok=True)
        post_input(folder / 'post.in', sections)
        self.stages.append(dict(id=stage_id, model=model_id, program=program, folder=stage_id, input='post.in', output='post.out', outputs=outputs, arguments=arguments or []))

    def save(self, method, analysis):
        manifest = dict(schema='highzyme.qe.workflow.v1', method=method, config=self.config, stages=self.stages,
                        models={name: {'symbols': atoms.get_chemical_symbols(), 'cell_A': atoms.cell.tolist(), 'formula': atoms.get_chemical_formula()} for name, atoms in self.atoms.items()},
                        requests=self.records, programs=self.programs, analysis=analysis)
        (self.folder / 'workflow.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        from highzyme.compute.workflow_runner import build_runner
        (self.folder / 'workflow-runner.sh').write_text(build_runner(manifest), encoding='utf-8', newline='\n')
        files = [file for file in self.folder.rglob('*') if file.is_file()]
        return {'manifest': manifest, 'required_programs': sorted({s['program'] for s in self.stages}),
                'input_files': [{'source': str(file), 'target': file.relative_to(self.folder).as_posix(), 'sha256': sha256(file)} for file in files]}


def convergence(work):
    options = work.config['convergence']
    parameter, values = options['parameter'], options['values']
    if parameter not in ('ecutwfc', 'kpoints') or len(values) < 2:
        raise ValueError('Convergence needs at least two ecutwfc or kpoints settings')
    if options['tolerance_eV_atom'] <= 0 or any(np.any(np.asarray(b) < np.asarray(a)) or np.array_equal(a, b) for a, b in zip(values[:-1], values[1:])):
        raise ValueError('Use an increasing parameter series and positive convergence tolerance')
    model = next(iter(work.models))
    rows = []
    for index, value in enumerate(values):
        changes = {'calculation': 'scf', parameter: value}
        if parameter == 'ecutwfc':
            changes['ecutrho'] = float(value) * float(options.get('density_ratio', 4))
        stage = work.pw('sample-' + str(index + 1), model, changes)
        rows.append(dict(stage=stage, value=value))
    return dict(samples=rows, parameter=parameter, tolerance_eV_atom=float(options['tolerance_eV_atom']))


def energy_models(work):
    return {name: work.pw(name, name) for name in work.models}


def reaction_energy(work):
    stages = energy_models(work)
    combinations = work.config.get('combinations')
    if 'states' in work.config:
        states = work.config['states']
        reference = next(s for s in states if s['id'] == work.config['reference_state'])
        combinations = [{**s, 'coefficients': {name: s['coefficients'].get(name, 0) - reference['coefficients'].get(name, 0) for name in work.models}} for s in states]
    if not combinations:
        raise ValueError('Reaction calculations require balanced states or energy combinations')
    analysis = dict(energy_stages=stages, combinations=combinations, energy_kind=work.config.get('energy_kind', 'electronic'), vibrations={})
    if analysis['energy_kind'] == 'free-energy':
        temperature = work.config['thermochemistry']['temperature_K']
        pressure = work.config['thermochemistry']['pressure_Pa']
        if temperature <= 0 or pressure <= 0:
            raise ValueError('Thermochemistry requires positive temperature and pressure')
        for name, model in work.models.items():
            if 'thermal_correction_eV' in model:
                if not model.get('thermal_source'):
                    raise ValueError('A supplied thermal correction requires its source')
                continue
            options = model['vibrations']
            if work.records[name]['parameters']['calculation'] != 'scf':
                raise ValueError('Vibrations require an already optimized structure and SCF forces')
            indices = options.get('indices', list(range(len(work.atoms[name]))))
            delta = float(options.get('delta_A', .01))
            if delta <= 0 or not indices or any(type(i) is not int or not 0 <= i < len(work.atoms[name]) for i in indices) or len(set(indices)) != len(indices):
                raise ValueError('Invalid vibration indices or displacement')
            displaced = []
            for atom in indices:
                for axis in range(3):
                    for sign, label in [(-1, 'minus'), (1, 'plus')]:
                        atoms = work.atoms[name].copy()
                        atoms.positions[atom, axis] += sign * delta
                        stage_id = name + '-vib-' + str(atom) + '-' + str(axis) + '-' + label
                        work.pw(stage_id, name, {'calculation': 'scf', 'fixed_atoms': [], 'fixed_cartesian': []}, atoms=atoms)
                        displaced.append(dict(stage=stage_id, atom=atom, axis=axis, sign=sign))
            analysis['vibrations'][name] = dict(options=options, indices=indices, delta_A=delta, displacements=displaced)
    return analysis


def electronic_structure(work):
    options = work.config['electronic']
    model = options.get('model', next(iter(work.models)))
    work.pw('ground-state', model, {'calculation': 'scf'}, shared=model)
    settings = {'calculation': 'nscf', 'kpoints': options['kpoints'], 'system': options.get('system', {})}
    work.pw('density-states', model, settings, shared=model)
    energy_options = {key: options[key] for key in ('Emin', 'Emax', 'DeltaE', 'degauss', 'ngauss') if key in options}
    work.post('dos', model, 'dos', {'DOS': {'prefix': 'highzyme', 'outdir': '../shared/' + model, 'fildos': 'dos.dat', **energy_options}}, ['dos.dat'])
    if options.get('pdos', True):
        work.post('pdos', model, 'projwfc', {'PROJWFC': {'prefix': 'highzyme', 'outdir': '../shared/' + model, 'filpdos': 'pdos', **energy_options}}, ['pdos.pdos_tot'])
    if options.get('bands'):
        band_options = options['bands']
        points = np.asarray(band_options['points'], dtype=float)
        if points.ndim != 2 or points.shape[1] != 3 or len(points) != len(band_options['labels']):
            raise ValueError('Band path needs matching reciprocal-space points and labels')
        count = int(band_options.get('points_per_segment', 15))
        if count < 2:
            raise ValueError('Use at least two points per band segment')
        path_points = np.concatenate([np.linspace(a, b, count, endpoint=False) for a, b in zip(points[:-1], points[1:])] + [points[-1:]])
        work.pw('band-path', model, {'calculation': 'bands', 'kpath': np.column_stack([path_points, np.ones(len(path_points))]).tolist(), 'system': options.get('system', {})}, shared=model)
        work.post('bands', model, 'bands', {'BANDS': {'prefix': 'highzyme', 'outdir': '../shared/' + model, 'filband': 'bands.dat'}}, ['bands.dat.gnu'])
        options['bands']['tick_indices'] = [i * count for i in range(len(points))]
    return {'model': model, 'options': options}


def charge_analysis(work):
    options = work.config['charge']
    if options.get('density_kind', 'valence') not in ('valence', 'all-electron'):
        raise ValueError('Choose valence or all-electron density')
    all_electron = options.get('density_kind') == 'all-electron'
    references = {}
    for model in work.models:
        work.pw(model, model, {'calculation': 'scf'}, shared=model)
        references[model] = {}
        for symbol in set(work.atoms[model].get_chemical_symbols()):
            text = Path(work.pseudos[symbol]).read_text(errors='replace')[:20000]
            if all_electron and not re.search(r'is_paw\s*=\s*["\'](?:T|true)', text, re.I):
                raise ValueError('All-electron charge reconstruction requires PAW pseudopotentials: ' + symbol)
            match = re.search(r'z_valence\s*=\s*["\']\s*([-+\d.eEdD]+)', text, re.I) or re.search(r'([-+\d.eEdD]+)\s+Z valence', text, re.I)
            if not match:
                raise ValueError('UPF has no valence-electron count: ' + symbol)
            from ase.data import atomic_numbers
            references[model][symbol] = atomic_numbers[symbol] if all_electron else float(match[1].replace('D', 'E'))
        work.post('density-' + model, model, 'pp', {'INPUTPP': {'prefix': 'highzyme', 'outdir': '../shared/' + model, 'filplot': 'density.pp', 'plot_num': 21 if all_electron else 0},
                  'PLOT': {'iflag': 3, 'output_format': 6, 'fileout': 'density.cube'}}, ['density.cube'])
        if model in options.get('bader_models', []):
            stage_id = 'bader-' + model
            (work.folder / stage_id).mkdir(exist_ok=True)
            work.stages.append(dict(id=stage_id, model=model, folder=stage_id, program='bader', output='post.out', arguments=['../density-' + model + '/density.cube'], outputs=['ACF.dat']))
    return dict(options=options, reference_electrons=references)


def neb_path(work):
    from ase.mep import NEB
    options = work.config['neb']
    first, last = work.atoms[options['initial']], work.atoms[options['final']]
    if first.get_chemical_symbols() != last.get_chemical_symbols() or not np.allclose(first.cell, last.cell):
        raise ValueError('NEB endpoints need identical atom ordering and simulation cells')
    count = int(options.get('images', 5))
    if count < 3:
        raise ValueError('NEB requires endpoints and at least one intermediate image')
    work.pw('neb', options['initial'], {'calculation': 'scf'}, shared='neb')
    stage = work.stages[-1]
    stage.update(program='neb', input='neb.in', output='neb.out', arguments=['-in', 'neb.in'], outputs=['highzyme.dat'])
    folder = work.folder / 'neb'
    first = read(folder / 'input.extxyz')
    last.set_constraint(first.constraints)
    images = [first] + [first.copy() for _ in range(count - 2)] + [last]
    NEB(images, method='improvedtangent').interpolate(method=options.get('interpolation', 'idpp'), mic=options.get('minimum_image', False), apply_constraint=True)
    text = (folder / 'qe.in').read_text()
    lines = text.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith('ATOMIC_POSITIONS'))
    flags = [line.split()[4:] for line in lines[index + 1:index + len(first) + 1]]
    engine = '\n'.join(lines[:index] + lines[index + len(first) + 1:])
    path_input = io.StringIO()
    parameters = {'string_method': 'neb', 'restart_mode': 'from_scratch', 'num_of_images': count, 'nstep_path': int(options.get('steps', 60)),
                  'path_thr': float(options['force_threshold_eV_A']), 'CI_scheme': 'auto' if options.get('climb', True) else 'no-CI', 'opt_scheme': options.get('optimizer', 'broyden'), 'first_last_opt': False}
    write_fortran_namelist(path_input, input_data={'PATH': parameters})
    path_text = path_input.getvalue().replace('EOF', '')
    positions = []
    for i, image in enumerate(images):
        positions += ['FIRST_IMAGE' if i == 0 else 'LAST_IMAGE' if i == count - 1 else 'INTERMEDIATE_IMAGE', 'ATOMIC_POSITIONS angstrom']
        for atom, mask in zip(image, flags):
            positions.append(atom.symbol + ' ' + ' '.join(format(v, '.12f') for v in atom.position) + (' ' + ' '.join(mask) if mask else ''))
    (folder / 'neb.in').write_text('BEGIN\nBEGIN_PATH_INPUT\n' + path_text + '\nEND_PATH_INPUT\nBEGIN_ENGINE_INPUT\n' + engine + '\nBEGIN_POSITIONS\n' + '\n'.join(positions) + '\nEND_POSITIONS\nEND_ENGINE_INPUT\nEND\n', encoding='utf-8', newline='\n')
    write(folder / 'input-images.extxyz', images)
    return dict(options=options, parameters=parameters)


def prepare(request):
    work = Workflow(request)
    method = work.config['method']
    if method == 'convergence':
        analysis = convergence(work)
    elif method in ('adsorption', 'formation-energy'):
        analysis = dict(energy_stages=energy_models(work), combinations=work.config['combinations'])
    elif method == 'reaction-energy':
        analysis = reaction_energy(work)
    elif method == 'electronic-structure':
        analysis = electronic_structure(work)
    elif method == 'charge-analysis':
        analysis = charge_analysis(work)
    elif method == 'neb':
        analysis = neb_path(work)
    else:
        raise ValueError('Unknown scientific workflow: ' + method)
    if 'combinations' in analysis:
        energy_combinations({'analysis': analysis}, {name: dict(energy_eV=0., symbols=atoms.get_chemical_symbols()) for name, atoms in work.atoms.items()})
    return work.save(method, analysis)


def pw_result(folder, stage, record):
    text = (folder / stage['folder'] / stage['output']).read_text(encoding='utf-8', errors='replace')
    matches = re.findall(r'!\s+total energy\s*=\s*([-+\d.EeDd]+)\s+Ry', text)
    geometry = stage['calculation'] in ('relax', 'vc-relax')
    if not matches or 'JOB DONE.' not in text or 'convergence NOT achieved' in text or geometry and not re.search(r'End of BFGS Geometry Optimization|bfgs converged', text, re.I):
        raise ValueError('Unfinished or unconverged PW stage: ' + stage['id'])
    energy = float(matches[-1].replace('D', 'E').replace('d', 'e')) * Rydberg
    atoms = read(folder / stage['folder'] / stage['output'], format='espresso-out', index=-1)
    final = folder / stage['folder'] / 'final.extxyz'
    write(final, atoms)
    return dict(energy_eV=energy, formula=atoms.get_chemical_formula(), atom_count=len(atoms), symbols=atoms.get_chemical_symbols(),
                calculation=record['parameters']['calculation'], structure=final.relative_to(folder).as_posix())


def energy_combinations(manifest, models):
    rows = []
    for combination in manifest['analysis']['combinations']:
        coefficients = combination['coefficients']
        balance = Counter()
        energy = 0.
        for name, coefficient in coefficients.items():
            if name not in models or not np.isfinite(coefficient):
                raise ValueError('Unknown model or invalid coefficient: ' + name)
            energy += coefficient * models[name]['energy_eV']
            for element, number in Counter(models[name]['symbols']).items():
                balance[element] += coefficient * number
        if any(abs(value) > 1e-8 for value in balance.values()):
            raise ValueError('Energy combination is not element-balanced: ' + combination['id'])
        rows.append(dict(id=identifier(combination['id']), label=combination.get('label', combination['id']), energy_eV=energy, coefficients=coefficients))
    return rows


def export_result(folder, manifest, result, job, language):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from highzyme.tools.figure_style import figure_rc, figure_size, series_style, EXPORT_DPI, PROFILE
    result.update(schema='highzyme.qe.workflow.result.v1', method=manifest['method'], job={k: job.get(k) for k in ('id', 'scheduler_id', 'status', 'resources')}, plot_profile=PROFILE)
    files = {'result': 'result.json', 'request': 'workflow.json', 'report': 'report.md'}
    for index, chart in enumerate(result.get('charts', [])):
        with plt.rc_context(figure_rc()):
            fig, ax = plt.subplots(figsize=figure_size(), layout='constrained')
            for i, series in enumerate(chart['series']):
                style = series_style(series.get('color_index', i))
                if chart['id'] in ('dos', 'pdos', 'bands', 'charge-difference'):
                    style['marker'] = None
                    style['linestyle'] = '-'
                ax.plot(series['x'], series['y'], label=series['label'], **{key: style[key] for key in ('color', 'marker', 'linestyle')})
            ax.set(xlabel=chart.get('x_math', chart['x_label']), ylabel=chart.get('y_math', chart['y_label']))
            if chart.get('x_ticks'):
                ax.set_xticks(chart['x_ticks']['positions'], chart['x_ticks']['labels'], rotation=25, ha='right')
            if chart.get('zero_line'):
                (ax.axvline if chart.get('zero_axis') == 'x' else ax.axhline)(0, color='#6F747B', linestyle='--', linewidth=.6)
            if chart['id'] == 'bands':
                for position in chart['x_ticks']['positions']:
                    ax.axvline(position, color='#6F747B', alpha=.3, linewidth=.5)
            if (1 < len(chart['series']) <= 8 or chart['id'] == 'pdos') and chart.get('legend', True):
                ax.legend()
            for fmt in ('png', 'svg', 'pdf'):
                name = 'figure-' + str(index + 1) + '.' + fmt
                fig.savefig(folder / name, dpi=EXPORT_DPI)
                files['figure_' + str(index + 1) + '_' + fmt] = name
            plt.close(fig)
    for table in result.get('tables', []):
        if not table['rows']:
            continue
        name = identifier(table['id']) + '.csv'
        with (folder / name).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(table['rows'][0]))
            writer.writeheader()
            writer.writerows({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in table['rows'])
        files[table['id']] = name
    (folder / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    names = {'convergence': '参数收敛', 'adsorption': '吸附与结合能', 'formation-energy': '缺陷与位点稳定性', 'electronic-structure': '电子结构', 'charge-analysis': '电荷分析', 'reaction-energy': '反应能与自由能', 'neb': '反应路径与势垒'}
    title = names[manifest['method']] if language == 'zh' else 'NEB' if manifest['method'] == 'neb' else manifest['method'].replace('-', ' ').capitalize()
    lines = ['# ' + title, '', ('状态：' if language == 'zh' else 'Status: ') + result['status'], '']
    for chart_index in range(len(result.get('charts', []))):
        lines += ['![Calculation](figure-' + str(chart_index + 1) + '.svg)', '']
    lines += ['## ' + ('计算记录' if language == 'zh' else 'Calculation record'), '', '```json', json.dumps({k: v for k, v in result.items() if k not in ('charts', 'volume')}, indent=2, ensure_ascii=False), '```', '']
    (folder / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    return {'result': result, 'files': files}


def collect(request):
    folder = Path(request['directory'])
    manifest = json.loads((folder / 'workflow.json').read_text())
    progress_file = folder / 'workflow-status.json'
    progress = json.loads(progress_file.read_text()) if progress_file.exists() else {'status': 'failed', 'error': 'Workflow status was not retrieved'}
    result = dict(status='completed', charts=[], tables=[], structures=[], progress=progress)
    if progress['status'] != 'completed' or request['job']['status'] != 'completed':
        result.update(status='failed', error=progress.get('error') or 'Scheduler did not complete the workflow')
        return export_result(folder, manifest, result, request['job'], request.get('language', 'en'))
    models = {}
    for stage in manifest['stages']:
        if stage['program'] == 'pw' and stage['calculation'] in ('scf', 'relax', 'vc-relax') and '-vib-' not in stage['id']:
            models[stage['id']] = pw_result(folder, stage, manifest['requests'][stage['id']])
            result['structures'].append({'label': stage['id'], 'file': models[stage['id']]['structure']})
    extra_files = {}
    if manifest['method'] == 'convergence':
        samples = manifest['analysis']['samples']
        reference = models[samples[-1]['stage']]['energy_eV']
        rows = [dict(sample=index + 1, value=sample['value'], energy_eV=models[sample['stage']]['energy_eV'],
                     delta_eV_atom=(models[sample['stage']]['energy_eV'] - reference) / models[sample['stage']]['atom_count']) for index, sample in enumerate(samples)]
        tolerance = manifest['analysis']['tolerance_eV_atom']
        selected = next((i for i in range(len(rows) - 1) if all(abs(r['delta_eV_atom']) <= tolerance for r in rows[i:])), None)
        result.update(reference_stage=samples[-1]['stage'], converged_setting=rows[selected]['value'] if selected is not None else None, tolerance_eV_atom=tolerance)
        result['tables'].append(dict(id='convergence', rows=rows))
        cutoff_series = manifest['analysis']['parameter'] == 'ecutwfc'
        result['charts'].append(dict(id='convergence', x_label='Wavefunction cutoff (Ry)' if cutoff_series else 'k-point grid sample', y_label='Relative energy (eV/atom)', series=[dict(label='Energy difference', x=[r['value'] if cutoff_series else r['sample'] for r in rows], y=[r['delta_eV_atom'] for r in rows])]))
    elif manifest['method'] == 'electronic-structure':
        from highzyme.compute.qe_analysis import electronic_result
        electronic_result(folder, manifest, result)
    elif manifest['method'] == 'charge-analysis':
        from highzyme.compute.qe_analysis import charge_result
        extra_files = charge_result(folder, manifest, result)
    elif manifest['method'] == 'neb':
        data = np.loadtxt(folder / 'neb/highzyme.dat', ndmin=2)
        relative = data[:, 1] - data[0, 1]
        result['barrier_eV'] = float(relative.max())
        result['reverse_barrier_eV'] = float(data[:, 1].max() - data[-1, 1])
        result['tables'].append(dict(id='neb-path', rows=[dict(image=i + 1, coordinate=float(row[0]), energy_relative_eV=float(relative[i]), **({'force_error_eV_A': float(row[2])} if len(row) > 2 else {})) for i, row in enumerate(data)]))
        result['charts'].append(dict(id='neb-path', x_label='Normalized reaction coordinate', y_label='Relative energy (eV)', series=[dict(label='CI-NEB' if manifest['analysis']['options'].get('climb', True) else 'NEB', x=data[:, 0].tolist(), y=relative.tolist())]))
        result['conditions'] = manifest['analysis']['parameters']
        if (folder / 'neb/highzyme.xyz').exists():
            for i, atoms in enumerate(read(folder / 'neb/highzyme.xyz', index=':')):
                target = 'neb/image-' + str(i + 1) + '.extxyz'
                write(folder / target, atoms)
                result['structures'].append(dict(label='image-' + str(i + 1), file=target))
    else:
        energy = {name: models[stage] for name, stage in manifest['analysis']['energy_stages'].items()}
        rows = energy_combinations(manifest, energy)
        free_energy = manifest['analysis'].get('energy_kind') == 'free-energy'
        if free_energy:
            from highzyme.compute.qe_analysis import thermal_corrections
            thermal, details = thermal_corrections(folder, manifest, energy)
            for row in rows:
                row['electronic_eV'] = row['energy_eV']
                row['thermal_correction_eV'] = sum(coefficient * thermal[name] for name, coefficient in row['coefficients'].items())
                row['energy_eV'] += row['thermal_correction_eV']
            result['thermochemistry'] = details
            result['conditions'] = manifest['config']['thermochemistry']
        result['tables'].append(dict(id='energy-comparison', rows=rows))
        result['charts'].append(dict(id='energy-comparison', x_label='Reaction state' if manifest['method'] == 'reaction-energy' else 'Configuration', y_label='Free energy change (eV)' if free_energy else 'Energy change (eV)', zero_line=True, x_ticks=dict(positions=list(range(len(rows))), labels=[r['label'] for r in rows]), series=[dict(label=manifest['method'], x=list(range(len(rows))), y=[r['energy_eV'] for r in rows])]))
    result['models'] = models
    exported = export_result(folder, manifest, result, request['job'], request.get('language', 'en'))
    exported['files'].update(extra_files)
    exported['files'].update({'structure_' + s['label']: s['file'] for s in result['structures']})
    return exported


if __name__ == '__main__':
    try:
        request = json.load(sys.stdin)
        result = prepare(request) if request['action'] == 'prepare' else collect(request)
        print(json.dumps({'result': result}, ensure_ascii=False, allow_nan=False))
    except Exception as error:
        print(json.dumps({'error': str(error)}))
        sys.exit(1)
