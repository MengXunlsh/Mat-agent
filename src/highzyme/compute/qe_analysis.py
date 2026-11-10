"""Postprocess saved QE numeric files without repeating a calculation."""
from __future__ import annotations

from collections import Counter
import io
from pathlib import Path
import re
import tempfile

import numpy as np
from ase.io import read
from ase.io.cube import read_cube, write_cube
from ase.units import Bohr


def energy_reference(text, options):
    if 'energy_reference_eV' in options:
        return float(options['energy_reference_eV']), 'user-provided'
    for pattern, kind in [(r'(?:the\s+)?Fermi energy is\s*([-+\d.Ee]+)', 'fermi'),
                          (r'EFermi\s*=\s*([-+\d.Ee]+)', 'fermi'),
                          (r'highest occupied(?:, lowest unoccupied)? level[^:]*:\s*([-+\d.Ee]+)', 'vbm')]:
        found = re.findall(pattern, text, re.I)
        if found:
            return float(found[-1]), kind
    raise ValueError('No energy reference was found; supply energy_reference_eV')


def electronic_result(folder, manifest, result):
    options = manifest['analysis']['options']
    dos_file = folder / 'dos/dos.dat'
    text = (folder / 'density-states/qe.out').read_text(errors='replace') + '\n' + dos_file.read_text()
    reference, kind = energy_reference(text, options)
    dos = np.loadtxt(dos_file, ndmin=2)
    spin = dos.shape[1] == 4
    series = [dict(label='DOS ↑' if spin else 'DOS', x=(dos[:, 0] - reference).tolist(), y=dos[:, 1].tolist())]
    if spin:
        series.append(dict(label='DOS ↓', x=(dos[:, 0] - reference).tolist(), y=dos[:, 2].tolist()))
    energy_axis = dict(label='Energy relative to reference (eV)', math=r'$E-E_{\mathrm{ref}}$ (eV)', rich='E − E{ref|ref} (eV)')
    result['charts'].append(dict(id='dos', x_label=energy_axis['label'], x_math=energy_axis['math'], x_rich=energy_axis['rich'], y_label='DOS (states/eV)', series=series, zero_line=True, zero_axis='x'))
    rows = [dict(energy_eV=float(row[0]), energy_relative_eV=float(row[0] - reference), dos_up=float(row[1]), **({'dos_down': float(row[2])} if spin else {})) for row in dos]
    result['tables'].append(dict(id='density-of-states', rows=rows))
    centers, projected = [], []
    for group in options.get('pdos_groups', []):
        indices = set(group['atoms'])
        datasets = []
        for file in (folder / 'pdos').glob('pdos.pdos_atm*'):
            match = re.search(r'atm#(\d+)\(([^)]+)\)_wfc#\d+\(([^)]+)\)', file.name)
            if match and int(match[1]) - 1 in indices and match[3] == group['orbital']:
                data = np.loadtxt(file, ndmin=2)
                values = data[:, 1] + data[:, 2] if spin else data[:, 1]
                datasets.append((data[:, 0] - reference, values))
        if not datasets:
            raise ValueError('No matching projected states for: ' + group['id'])
        x = datasets[0][0]
        if any(not np.allclose(x, item[0]) for item in datasets):
            raise ValueError('Projected DOS energy grids differ')
        y = sum(item[1] for item in datasets)
        projected.append(dict(label=group.get('label', group['id']), x=x.tolist(), y=y.tolist()))
        if 'window_eV' in group:
            low, high = group['window_eV']
            selected = (x >= low) & (x <= high)
            if selected.sum() < 2:
                raise ValueError('Band-center window contains fewer than two samples')
            area = np.trapezoid(y[selected], x[selected])
            center = float(np.trapezoid(x[selected] * y[selected], x[selected]) / area) if area > 0 else None
            centers.append(dict(group=group['id'], orbital=group['orbital'], window_eV=[low, high], center_relative_eV=center, energy_reference=kind))
    if projected:
        result['charts'].append(dict(id='pdos', x_label=energy_axis['label'], x_math=energy_axis['math'], x_rich=energy_axis['rich'], y_label='PDOS (states/eV)', series=projected, zero_line=True, zero_axis='x'))
    if centers:
        result['tables'].append(dict(id='band-centers', rows=centers))
    if options.get('bands'):
        blocks = [np.loadtxt(io.StringIO(block), ndmin=2) for block in re.split(r'\n\s*\n', (folder / 'bands/bands.dat.gnu').read_text().strip()) if block.strip()]
        if not blocks:
            raise ValueError('Empty band output')
        plot = dict(id='bands', x_label='Reciprocal-space path', y_label=energy_axis['label'], y_math=energy_axis['math'], y_rich=energy_axis['rich'], legend=False, series=[dict(label='Band ' + str(i + 1), color_index=0, x=block[:, 0].tolist(), y=(block[:, 1] - reference).tolist()) for i, block in enumerate(blocks)])
        ticks = options['bands']['tick_indices']
        plot['x_ticks'] = dict(positions=[float(blocks[0][i, 0]) for i in ticks], labels=options['bands']['labels'])
        result['charts'].append(plot)
        result['tables'].append(dict(id='bands', rows=[dict(band=i + 1, path=float(row[0]), energy_relative_eV=float(row[1] - reference)) for i, block in enumerate(blocks) for row in block]))
    result['conditions'] = dict(energy_reference_eV=reference, energy_reference=kind, pdos_moment='spin-summed first moment in the specified window')


def cube_data(file):
    with Path(file).open() as stream:
        return read_cube(stream)


def charge_result(folder, manifest, result):
    from scipy.ndimage import zoom
    options = manifest['analysis']['options']
    model_data = {name: cube_data(folder / ('density-' + name) / 'density.cube') for name in manifest['models']}
    terms = options['coefficients']
    template = model_data[options.get('display_model', next(iter(terms)))]
    data = np.zeros_like(template['data'])
    for name, coefficient in terms.items():
        source = model_data[name]
        if source['data'].shape != data.shape or not np.allclose(source['atoms'].cell, template['atoms'].cell) or not np.allclose(source['origin'], template['origin']):
            raise ValueError('Charge-density grids, origins and cells must match')
        data += coefficient * source['data']
    density = data / Bohr ** 3
    with (folder / 'charge-difference.cube').open('w') as stream:
        write_cube(stream, template['atoms'], data, origin=template['origin'], comment='Density difference (electrons/bohr^3)')
    axes = np.arange(data.shape[2]) * np.linalg.norm(template['atoms'].cell[2]) / data.shape[2]
    averaged = density.mean(axis=(0, 1))
    result['charts'].append(dict(id='charge-difference', x_label='Distance along c (Å)', y_label='Mean density difference (e/Å³)', series=[dict(label='Density difference', x=axes.tolist(), y=averaged.tolist())], zero_line=True))
    result['tables'].append(dict(id='planar-charge', rows=[dict(distance_A=float(x), density_e_A3=float(y)) for x, y in zip(axes, averaged)]))
    preview = zoom(data, [min(32, n) / n for n in data.shape], order=1, mode='grid-wrap', grid_mode=True)
    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as stream:
        write_cube(stream, template['atoms'], preview, origin=template['origin'])
        stream.seek(0)
        cube = stream.read()
    result['volume'] = dict(cube=cube, model_label=options.get('display_model', next(iter(terms))), level=float(options.get('isosurface', max(abs(data.max()), abs(data.min())) * .2)), unit='e/bohr³', preview_shape=list(preview.shape), source_shape=list(data.shape))
    result['conditions'] = dict(density_kind=options.get('density_kind', 'valence'), coefficients=terms, integrated_difference_e=float(density.sum() * template['atoms'].cell.volume / data.size))
    for model in options.get('bader_models', []):
        rows = []
        electrons = manifest['analysis']['reference_electrons'][model]
        for line in (folder / ('bader-' + model) / 'ACF.dat').read_text().splitlines():
            fields = line.split()
            if len(fields) >= 7 and fields[0].isdigit():
                index = int(fields[0]) - 1
                symbol = manifest['models'][model]['symbols'][index]
                population = float(fields[4])
                rows.append(dict(atom=index, element=symbol, partition_electrons=population, reference_electrons=electrons[symbol], net_charge_e=electrons[symbol] - population))
        if len(rows) != len(manifest['models'][model]['symbols']):
            raise ValueError('Bader output does not match the structure atom count')
        result['tables'].append(dict(id='bader-' + model, rows=rows))
    return {'charge_volume': 'charge-difference.cube'}


def thermal_corrections(folder, manifest, energy):
    from ase.thermochemistry import HarmonicThermo, IdealGasThermo
    from ase.vibrations.data import VibrationsData
    from ase.units import invcm
    corrections, records = {}, {}
    conditions = manifest['config']['thermochemistry']
    for model in manifest['config']['models']:
        name = model['id']
        additions = model.get('corrections', [])
        if any(not row.get('source') for row in additions):
            raise ValueError('Additional free-energy corrections require a source')
        if 'thermal_correction_eV' in model:
            corrections[name] = float(model['thermal_correction_eV']) + sum(float(row['value_eV']) for row in additions)
            records[name] = dict(source=model['thermal_source'], correction_eV=corrections[name], additional_corrections=additions, method='supplied')
            continue
        plan = manifest['analysis']['vibrations'][name]
        indices = plan['indices']
        atoms = read(folder / name / 'input.extxyz')
        hessian = np.zeros((3 * len(indices), 3 * len(indices)))
        forces = {}
        for displacement in plan['displacements']:
            output = read(folder / displacement['stage'] / 'qe.out', format='espresso-out', index=-1)
            forces[(displacement['atom'], displacement['axis'], displacement['sign'])] = output.get_forces()[indices].reshape(-1)
        for i, atom in enumerate(indices):
            for axis in range(3):
                hessian[3 * i + axis] = -(forces[(atom, axis, 1)] - forces[(atom, axis, -1)]) / (2 * plan['delta_A'])
        hessian = (hessian + hessian.T) / 2
        frequencies = VibrationsData.from_2d(atoms, hessian, indices=indices).get_energies()
        options = plan['options']
        method = options['model']
        selected = frequencies
        if method == 'ideal-gas':
            if len(indices) != len(atoms):
                raise ValueError('Ideal-gas thermochemistry requires vibrations for all molecule atoms')
            count = {'linear': max(0, 3 * len(atoms) - 5), 'nonlinear': max(0, 3 * len(atoms) - 6), 'monatomic': 0}[options['geometry']]
            selected = sorted(frequencies, key=np.abs)[-count:] if count else []
        elif method != 'harmonic':
            raise ValueError('Select ideal-gas or harmonic thermochemistry')
        if any(abs(complex(value).imag) > 1e-8 for value in selected):
            raise ValueError('Imaginary vibrational modes remain in ' + name + '; inspect the structure and displacement settings')
        selected = np.asarray(selected).real
        if method == 'ideal-gas':
            atoms.pbc = False
            thermo = IdealGasThermo(vib_energies=selected, geometry=options['geometry'], atoms=atoms, symmetrynumber=options['symmetrynumber'], spin=options['spin'], vib_selection='exact')
            correction = thermo.get_gibbs_energy(conditions['temperature_K'], conditions['pressure_Pa'], verbose=False)
        else:
            floor = float(options.get('minimum_frequency_cm1', 0)) * invcm
            selected = np.maximum(selected, floor)
            if np.any(selected <= 0):
                raise ValueError('Zero modes need an explicit low-frequency treatment in ' + name)
            correction = HarmonicThermo(vib_energies=selected).get_helmholtz_energy(conditions['temperature_K'], verbose=False)
        correction += sum(float(row['value_eV']) for row in additions)
        corrections[name] = float(correction)
        records[name] = dict(method=method, frequencies_cm1=[dict(real=float(complex(v).real / invcm), imaginary=float(complex(v).imag / invcm)) for v in frequencies],
                             thermal_frequencies_cm1=(selected / invcm).tolist(), excluded_rigid_modes=len(frequencies) - len(selected),
                             correction_eV=float(correction), additional_corrections=additions, low_frequency_floor_cm1=options.get('minimum_frequency_cm1'),
                             basis='Ideal-gas Gibbs energy' if method == 'ideal-gas' else 'Harmonic Helmholtz energy; surface pV contribution neglected')
    return corrections, records
