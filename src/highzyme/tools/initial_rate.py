"""Initial-rate Michaelis-Menten fitting and self-contained reproducible exports."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import warnings

import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit
from highzyme.tools.tables import read_table as _read_table, inspect_table
from highzyme.tools.figure_style import figure_rc, figure_size, series_style, EXPORT_DPI, PROFILE


def read_table(file, sheet=None):
    headers, rows, sheets, _ = _read_table(file, sheet)
    return headers, rows, sheets


def michaelis_menten(substrate, km, vmax):
    return vmax * substrate / (km + substrate)


def fit_initial_rates(request):
    headers, rows, sheets = read_table(request['file'], request.get('sheet'))
    if len(sheets) > 1 and not request.get('sheet'):
        raise ValueError('Select an XLSX sheet before fitting')
    columns = [request['concentration_column'], request['rate_column']]
    if request.get('sigma_column'):
        columns.append(request['sigma_column'])
    if len(set(columns)) != len(columns) or any(c not in headers for c in columns):
        raise ValueError('Select distinct existing concentration, rate and optional sigma columns')
    units = [str(request.get(key, '')).strip() for key in ('concentration_unit', 'rate_unit')]
    if not all(units):
        raise ValueError('Specify concentration and initial-rate units')
    group_columns = request.get('group_columns') or []
    context_columns = request.get('context_columns') or []
    for selected in (group_columns, context_columns):
        if not isinstance(selected, list) or any(c not in headers for c in selected) or len(set(selected)) != len(selected):
            raise ValueError('Group/context columns must be distinct existing columns')
    if set(group_columns + context_columns) & set(columns):
        raise ValueError('Group/context columns must differ from numeric fit columns')
    groups = {}
    for row in rows:
        key = tuple(str(row[headers.index(c)] if row[headers.index(c)] is not None else '').strip() for c in group_columns)
        if any(not v for v in key):
            raise ValueError('Group columns cannot contain missing values')
        groups.setdefault(key, []).append(row)
    if len(groups) > 12:
        raise ValueError('Select at most 12 groups per analysis')
    results = []
    for key, subset in groups.items():
        context = {}
        for column in context_columns:
            values = {str(row[headers.index(column)]).strip() for row in subset}
            if len(values) != 1 or next(iter(values)) in ('', 'None'):
                raise ValueError('Condition varies or is missing within group: ' + column + ' / ' + str(key))
            context[column] = next(iter(values))
        try:
            fitted = fit_rows(headers, subset, columns, units)
        except ValueError as exc:
            raise ValueError((' / '.join(key) + ': ' if key else '') + str(exc)) from exc
        fitted.update(group=dict(zip(group_columns, key)), label=' / '.join(key), context=context)
        results.append(fitted)
    return {'groups': results, 'group_columns': group_columns, 'concentration_unit': units[0], 'rate_unit': units[1]} if group_columns else results[0]


def fit_rows(headers, rows, columns, units):
    try:
        values = np.asarray([[float(row[headers.index(c)]) for c in columns] for row in rows], dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError('Selected columns must contain numeric values without missing cells') from exc
    x, y = values[:, 0], values[:, 1]
    sigma = values[:, 2] if values.shape[1] == 3 else None
    if not np.isfinite(values).all() or (x < 0).any() or (y < 0).any():
        raise ValueError('Concentrations and rates must be finite and nonnegative; check blank correction for negative rates')
    if len(x) < 4 or len(np.unique(x[x > 0])) < 3 or np.ptp(y) <= 0:
        raise ValueError('Fit needs at least four observations, three distinct positive concentrations and varying rates')
    if sigma is not None and (sigma <= 0).any():
        raise ValueError('Rate standard deviations must be positive')
    # Nondimensional fitting avoids tolerance failures for molar-scale rates.
    xscale, yscale = float(x.max()), float(y.max())
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter('always', OptimizeWarning)
        parameters, covariance = curve_fit(michaelis_menten, x / xscale, y / yscale,
            p0=[np.median(x[x > 0]) / xscale, 1.2], bounds=(1e-12, np.inf),
            sigma=None if sigma is None else sigma / yscale, absolute_sigma=sigma is not None,
            max_nfev=20000, ftol=1e-12, xtol=1e-12, gtol=1e-12)
    km, vmax = parameters * [xscale, yscale]
    prediction = michaelis_menten(x, km, vmax)
    residual = y - prediction
    r2 = 1 - float(residual @ residual) / float(np.sum((y - y.mean())**2))
    standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0)) * [xscale, yscale]
    diagnostics = []
    if notices or not np.isfinite(covariance).all():
        diagnostics.append('Parameter uncertainty could not be estimated reliably.')
    if x.max() < km:
        diagnostics.append('All sampled concentrations are below fitted Km; the data do not reach half of fitted Vmax.')
    return {'model': 'v = Vmax * S / (Km + S)', 'method': 'nonlinear least squares',
            'weighted': sigma is not None, 'n': len(x), 'concentration_unit': units[0], 'rate_unit': units[1],
            'km': float(km), 'vmax': float(vmax),
            'standard_errors': {name: float(value) if np.isfinite(value) else None
                                for name, value in zip(('km', 'vmax'), standard_errors)},
            'r_squared': r2, 'rmse': float(np.sqrt(np.mean(residual**2))),
            'concentration': x.tolist(), 'initial_rate': y.tolist(),
            'sigma': None if sigma is None else sigma.tolist(),
            'fitted_rate': prediction.tolist(), 'residual': residual.tolist(), 'warnings': diagnostics}


def plot_fit(result, prefix, layout='overlay', labels=None):
    if layout not in ('overlay', 'panels'):
        raise ValueError('Plot layout must be overlay or panels')
    groups = result.get('groups', [result])
    labels = labels or [g.get('label') or 'Initial rates' for g in groups]
    if len(labels) != len(groups) or any(not isinstance(label, str) or not label.strip() for label in labels):
        raise ValueError('Supply one nonempty plot label per group')
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    count = len(groups) if layout == 'panels' else 1
    cols = min(2, count); rows = (count + cols - 1) // cols
    with plt.rc_context(figure_rc()):
        fig, axes = plt.subplots(rows, cols, figsize=figure_size(cols, rows), layout='constrained', squeeze=False)
        for i, (group, label) in enumerate(zip(groups, labels)):
            ax = axes.flat[i if layout == 'panels' else 0]
            style = series_style(i)
            grid = np.linspace(0, max(group['concentration']), 250)
            ax.errorbar(group['concentration'], group['initial_rate'], yerr=group['sigma'], fmt=style['marker'],
                        ms=3.6, color=style['color'], markeredgecolor='white', markeredgewidth=.35,
                        elinewidth=.65, capsize=1.8, label=label, zorder=3)
            ax.plot(grid, michaelis_menten(grid, group['km'], group['vmax']), color=style['color'], linestyle=style['linestyle'])
            ax.set(xlabel=f"Substrate concentration ({group['concentration_unit']})", ylabel=f"Initial rate ({group['rate_unit']})")
            ax.legend()
        for ax in list(axes.flat)[count:]:
            ax.set_visible(False)
        files = {key: str(prefix) + suffix for key, suffix in {'png': '-curve.png', 'svg': '-curve.svg'}.items()}
        for file in files.values():
            fig.savefig(file, dpi=EXPORT_DPI)
        plt.close(fig)
    return files


def replot_fit(request):
    result = json.loads(Path(request['file']).read_text(encoding='utf-8'))
    groups = result.get('groups', [result])
    for group in groups:
        if group.get('model') != 'v = Vmax * S / (Km + S)' or not group.get('concentration'):
            raise ValueError('Choose a saved Highzyme initial-rate result JSON')
    prefix = Path(request['output_prefix']); prefix.parent.mkdir(parents=True, exist_ok=True)
    options = {'layout': request.get('plot_layout', 'overlay'), 'labels': request.get('labels')}
    files = plot_fit(result, prefix, **options)
    config = str(prefix) + '-plot.json'
    Path(config).write_text(json.dumps({'result_file': request.get('source_label', Path(request['file']).name),
        'result_sha256': hashlib.sha256(Path(request['file']).read_bytes()).hexdigest(), 'profile': PROFILE, **options}, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'files': {**files, 'plot_options': config}, 'refitted': False}


def export_fit(request):
    result = fit_initial_rates(request)
    if request.get('plot_layout', 'overlay') not in ('overlay', 'panels'):
        raise ValueError('Plot layout must be overlay or panels')
    source = Path(request['file']); prefix = Path(request['output_prefix'])
    groups = result.get('groups', [result]); grouped = 'groups' in result
    result['source'] = {'file': request.get('source_label', source.name),
                        'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'sheet': request.get('sheet'),
                        'columns': {k: request.get(k) for k in ('concentration_column', 'rate_column', 'sigma_column', 'group_columns', 'context_columns')}}
    result['assay_context'] = request.get('assay_context', '')
    import scipy
    result['software'] = {'numpy': np.__version__, 'scipy': scipy.__version__}
    suffixes = {'data': '-data.csv', 'result': '-result.json', 'report': '-report.md',
        'png': '-curve.png', 'svg': '-curve.svg', 'request': '-input.json', 'script': '-reproduce.py', 'plot_options': '-plot.json'}
    if grouped:
        suffixes['parameters'] = '-parameters.csv'
    outputs = {key: prefix.with_name(prefix.name + suffix) for key, suffix in suffixes.items()}
    prefix.parent.mkdir(parents=True, exist_ok=True)
    group_columns = request.get('group_columns') or []
    context_columns = [c for c in request.get('context_columns', []) if c not in group_columns]
    # Canonical numerical names avoid collisions with user-supplied grouping headers.
    extra_columns = group_columns + context_columns
    canonical = ['concentration', 'initial_rate', 'fitted_rate', 'residual', 'sigma']
    mapped = {c: 'context_' + str(i + 1) for i, c in enumerate(extra_columns)}
    weighted = groups[0]['weighted']
    with outputs['data'].open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow([mapped[c] for c in extra_columns] + canonical[:4] + (['sigma'] if weighted else []))
        for group in groups:
            extras = [group['group'].get(c, group['context'].get(c)) for c in extra_columns]
            for i in range(group['n']):
                writer.writerow(extras + [group[k][i] for k in canonical[:4]] + ([group['sigma'][i]] if weighted else []))
    outputs['result'].write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    reproduction = {**request, 'file': outputs['data'].name, 'concentration_column': 'concentration',
                    'rate_column': 'initial_rate', 'sigma_column': 'sigma' if weighted else None,
                    'group_columns': [mapped[c] for c in group_columns], 'context_columns': [mapped[c] for c in context_columns],
                    'sheet': None, 'source_label': outputs['data'].name, 'output_prefix': prefix.name + '-reproduced'}
    outputs['request'].write_text(json.dumps(reproduction, ensure_ascii=False, indent=2), encoding='utf-8')
    script = Path(__file__).read_text(encoding='utf-8')
    for module, statement in [('tables', 'from highzyme.tools.tables import read_table as _read_table, inspect_table'),
                              ('figure_style', 'from highzyme.tools.figure_style import figure_rc, figure_size, series_style, EXPORT_DPI, PROFILE')]:
        if statement in script.splitlines():
            source_text = Path(__file__).with_name(module + '.py').read_text(encoding='utf-8')
            if module == 'tables':source_text = source_text.replace('read_table(', '_read_table(')
            script = script.replace(statement + '\n', source_text + '\n', 1)
    outputs['script'].write_text(script, encoding='utf-8')
    parameter_rows = [[g['label'] or 'Series', g['n'], g['km'], g['standard_errors']['km'], g['concentration_unit'],
                       g['vmax'], g['standard_errors']['vmax'], g['rate_unit'], g['r_squared'], g['rmse']] for g in groups]
    if grouped:
        with outputs['parameters'].open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['group', 'n', 'km', 'km_se', 'km_unit', 'vmax', 'vmax_se', 'vmax_unit', 'r_squared', 'rmse'])
            writer.writerows(parameter_rows)
    zh = request.get('language', 'en') == 'zh'
    report = [('# 初始速率动力学拟合' if zh else '# Initial-rate kinetics fit'), '',
              '![Initial-rate fit](' + prefix.name + '-curve.svg)', '',
              'v = Vmax × S / (Km + S)', '',
              ('方法：原始数据非线性最小二乘；各组独立拟合，不拟合截距，不合并重复值。' if zh else 'Method: nonlinear least squares; independent fits per group, no fitted intercept or replicate averaging.'),
              ('权重：速率标准差。' if zh else 'Weights: rate standard deviations.') if weighted else ('权重：等权重。' if zh else 'Weights: equal.'), '',
              '| Group | n | Km | SE(Km) | Unit | Vmax | SE(Vmax) | Unit | R² | RMSE |', '|---|---|---|---|---|---|---|---|---|---|']
    for row in parameter_rows:
        report.append('| ' + ' | '.join(f'{v:.8g}' if isinstance(v, float) else str(v).replace('|', r'\|') for v in row) + ' |')
    report += ['', ('来源：' if zh else 'Source: ') + str(result['source']['file']), 'SHA-256: ' + result['source']['sha256'],
               ('实验条件：' if zh else 'Assay context: ') + (result['assay_context'] or ('未提供' if zh else 'Not supplied')),
               ('参数单位与输入一致；标准误差来自拟合协方差的局部近似。' if zh else 'Units follow the input; standard errors use the local covariance approximation.')]
    translated = {'Parameter uncertainty could not be estimated reliably.': '参数不确定性无法可靠估计。',
                  'All sampled concentrations are below fitted Km; the data do not reach half of fitted Vmax.': '采样浓度均低于拟合 Km，数据尚未达到拟合 Vmax 的一半。'}
    for group in groups:
        if group['context']:
            report += ['', (group['label'] or 'Series') + ': ' + json.dumps(group['context'], ensure_ascii=False)]
        report += ['- ' + (group['label'] + ': ' if group['label'] else '') + (translated.get(w, w) if zh else w) for w in group['warnings']]
    report += ['', '```', f"python {outputs['script'].name} {outputs['request'].name}", '```']
    outputs['report'].write_text('\n'.join(report) + '\n', encoding='utf-8')
    replot_fit({'file': str(outputs['result']), 'output_prefix': str(prefix), 'source_label': outputs['result'].name, 'plot_layout': request.get('plot_layout', 'overlay')})
    vectors = ('concentration', 'initial_rate', 'sigma', 'fitted_rate', 'residual')
    summary = {k: v for k, v in result.items() if k not in vectors and k != 'groups'}
    if grouped:
        summary['groups'] = [{k: v for k, v in g.items() if k not in vectors} for g in groups]
    return {'fit': summary, 'files': {k: str(v) for k, v in outputs.items()}}


if __name__ == '__main__':
    import sys
    config = Path(sys.argv[1]).resolve()
    request = json.loads(config.read_text(encoding='utf-8'))
    request['file'] = str(config.parent / request['file'])
    request['output_prefix'] = str(config.parent / request['output_prefix'])
    print(json.dumps(export_fit(request), ensure_ascii=False, allow_nan=False))
