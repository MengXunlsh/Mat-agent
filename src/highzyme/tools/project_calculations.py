"""Project-file adapters around the existing unit, optical and kinetic algorithms."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from highzyme.tools.analysis_outputs import export_analysis
from highzyme.tools.tables import read_table


def source_record(file, label=None):
    file = Path(file)
    if file.stat().st_size > 32 * 1024**2:
        raise ValueError('Source exceeds 32 MiB')
    return {'file': label or file.name, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}


def signal_inputs(request):
    payload = deepcopy(request.get('parameters') or {})
    payload['operation'] = request['operation']
    headers, rows, sheets, _ = read_table(request['file'], request.get('sheet'))
    if len(sheets) > 1 and not request.get('sheet'):
        raise ValueError('Select an XLSX sheet before analysis')
    mapping = request.get('columns') or {}
    expected = {'fit_calibration': ('x', 'y'), 'linear_readout': ('concentrations',),
                'quenching_correction': ('observed', 'correction_factors'), 'quantify': ('signal',)}
    if payload['operation'] not in expected or set(mapping) != set(expected[payload['operation']]):
        raise ValueError('Select the columns required for this signal operation')
    for key, column in mapping.items():
        if column not in headers:
            raise ValueError('Unknown data column: ' + column)
        try:
            payload[key] = [float(row[headers.index(column)]) for row in rows]
        except (TypeError, ValueError) as exc:
            raise ValueError('Selected signal columns must contain finite numeric data without missing cells') from exc
    if payload['operation'] != 'linear_readout':
        payload['source'] = request.get('source_label', Path(request['file']).name)
    if payload['operation'] == 'quantify':
        calibration_file = Path(request['calibration_file'])
        if calibration_file.stat().st_size > 32 * 1024**2:
            raise ValueError('Calibration file exceeds 32 MiB')
        calibration = json.loads(calibration_file.read_text(encoding='utf-8-sig'))
        if calibration.get('schema') != 'highzyme.calculation.v1' or calibration.get('calculation') != 'signal' or 'slope' not in calibration.get('data', {}):
            raise ValueError('Choose a saved linear calibration -result.json')
        payload['calibration'] = calibration['data']
    return payload


def signal_outputs(payload, data):
    op = payload['operation']
    if op == 'quantify':
        rows = [{'signal': y, 'concentration': x, 'within_calibration_range': good}
                for y, x, good in zip(data['signal'], data['concentrations'], data['within_range'])]
        return rows, None, {'observations': len(rows), 'x_unit': data['x_unit'], 'y_unit': data['y_unit'],
                            'within_range': sum(data['within_range'])}
    if op == 'fit_calibration':
        rows = [{'x': x, 'signal': y, 'fitted_signal': y-r, 'residual': r}
                for x, y, r in zip(data['x'], data['y'], data['residuals'])]
        ends = [min(data['x']), max(data['x'])]
        plot = {'x_label': 'Concentration (' + data['x_unit'] + ')', 'y_label': 'Signal (' + data['y_unit'] + ')',
                'series': [{'label': 'Observations', 'x': data['x'], 'y': data['y'], 'style': 'points'},
                           {'label': 'Linear fit', 'x': ends, 'y': [data['slope']*x+data['intercept'] for x in ends]}]}
        return rows, plot, {k: data[k] for k in ('slope', 'intercept', 'r_squared', 'n', 'x_unit', 'y_unit')}
    if op == 'linear_readout':
        rows = [{'channel': channel['label'], 'concentration': x, 'signal': y, 'within_range': good}
                for channel in data['channels'] for x, y, good in zip(data['concentrations'], channel['signals'], channel['within_source_range'])]
        return rows, None, {'channels': len(data['channels']), 'observations': len(data['concentrations']), 'x_unit': data['x_unit']}
    rows = [{'index': i+1, 'observed': a, 'corrected': b} for i, (a, b) in enumerate(zip(data['observed'], data['corrected']))]
    plot = {'x_label': 'Observation', 'y_label': 'Signal (supplied units)', 'series': [
        {'label': label, 'x': list(range(1, len(rows)+1)), 'y': data[key], 'style': 'points'}
        for label, key in [('Observed', 'observed'), ('Corrected', 'corrected')]]}
    return rows, plot, {'observations': len(rows), 'correction_source': payload['source']}


def quantify_signal(payload):
    from highzyme.tools.simulation import vector
    values = vector(payload['signal'], limit=5000)
    fit = payload['calibration']
    if payload.get('y_unit') != fit['y_unit']:
        raise ValueError('Signal units must match the saved calibration')
    if fit['slope'] == 0:
        raise ValueError('A zero-slope calibration cannot determine concentration')
    concentrations = (values-fit['intercept'])/fit['slope']
    within = (concentrations >= fit['range'][0]) & (concentrations <= fit['range'][1])
    return {'status': 'COMPLETED', 'data': {'signal': values.tolist(), 'concentrations': [float(v) if good else None for v, good in zip(concentrations, within)],
            'within_range': within.tolist(), 'x_unit': fit['x_unit'], 'y_unit': fit['y_unit'], 'calibration': fit},
            'method': {'name': 'Inverse of the saved linear calibration within its fitted concentration range'}}


def measure_images(request):
    import cv2
    import numpy as np
    from PIL import Image
    from importlib.metadata import version
    from highzyme.tools.figure_style import ROI_BGR
    rows, images, overlays = [], [], []
    mode = request.get('mode', 'whole_image')
    if mode not in ('whole_image', 'region', 'circle_rois'):
        raise ValueError('Choose whole_image, region or circle_rois')
    if not isinstance(request.get('files'), list) or not 1 <= len(request['files']) <= 24:
        raise ValueError('Select 1 to 24 PNG, JPEG or WebP images')
    for index, name in enumerate(request['files']):
        file = Path(name)
        if file.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('Supported images: PNG, JPEG, WebP')
        source = source_record(file, (request.get('source_labels') or request['files'])[index])
        with Image.open(file) as check:
            if check.width*check.height > 20_000_000:
                raise ValueError('Image exceeds 20 million pixels')
        bgr = cv2.imdecode(np.frombuffer(file.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError('Image could not be decoded')
        height, width = bgr.shape[:2]; regions = []
        overlay = bgr.copy()
        if mode == 'circle_rois':
            size = min(height, width)
            lower, upper = request.get('min_radius_fraction', .08), request.get('max_radius_fraction', .24)
            if not 0 < lower < upper <= .5:
                raise ValueError('Circle radius fractions must satisfy 0 < min < max <= 0.5')
            grey = cv2.GaussianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (5, 5), 1.2)
            circles = cv2.HoughCircles(grey, cv2.HOUGH_GRADIENT, 1.2, size*.32, param1=70, param2=22,
                                      minRadius=max(3, int(size*lower)), maxRadius=int(size*upper))
            for x, y, radius in sorted([] if circles is None else circles[0].tolist(), key=lambda c: (round(c[1]/max(1, size*.2)), c[0]))[:16]:
                mask = np.zeros((height, width), np.uint8)
                radius = max(2, round(radius*.65)); center = (round(x), round(y))
                cv2.circle(mask, center, radius, 255, -1)
                stroke = max(1, round(size/300))
                cv2.circle(overlay, center, radius, (255, 255, 255), stroke+2)
                cv2.circle(overlay, center, radius, ROI_BGR, stroke)
                regions.append(mask)
        else:
            box = request.get('region') if mode == 'region' else [0, 0, 1, 1]
            if not isinstance(box, list) or len(box) != 4 or not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1:
                raise ValueError('Region requires normalized [left, top, right, bottom]')
            left, top, right, bottom = [int(v*n) for v, n in zip(box, [width, height, width, height])]
            mask = np.zeros((height, width), np.uint8); mask[top:bottom, left:right] = 255
            stroke = max(1, round(min(width,height)/300))
            end = (min(right, width-1), min(bottom, height-1))
            cv2.rectangle(overlay, (left, top), end, (255, 255, 255), stroke+2)
            cv2.rectangle(overlay, (left, top), end, ROI_BGR, stroke)
            regions.append(mask)
        rgb, hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        for region, mask in enumerate(regions, 1):
            selected = mask > 0
            if selected.sum() < 20:
                raise ValueError('Selected region contains fewer than 20 pixels')
            mean, sd, color = rgb[selected].mean(0), rgb[selected].std(0), hsv[selected].mean(0)
            yy, xx = np.where(selected)
            rows.append({'file': source['file'], 'region': region, 'pixels': int(selected.sum()),
                         'left': float(xx.min()/width), 'top': float(yy.min()/height),
                         'right': float((xx.max()+1)/width), 'bottom': float((yy.max()+1)/height),
                         **dict(zip(['mean_r', 'mean_g', 'mean_b'], map(float, mean))),
                         **dict(zip(['std_r', 'std_g', 'std_b'], map(float, sd))),
                         **dict(zip(['mean_h', 'mean_s', 'mean_v'], map(float, color)))})
        images.append({**source, 'width': width, 'height': height, 'regions': len(regions),
                       'status': 'measured' if regions else 'no_circles_detected'})
        if request.get('output_prefix'):
            target = str(request['output_prefix']) + '-roi-' + str(index+1) + '.png'
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            cv2.imencode('.png', overlay)[1].tofile(target); overlays.append(target)
    return {'status': 'COMPLETED', 'data': {'images': images, 'mode': mode},
            'method': {'name': 'OpenCV RGB/HSV measurement in explicit image regions', 'libraries': {'opencv': version('opencv-python-headless')}},
            'summary': {'images': len(images), 'measured_regions': len(rows), 'hsv_scale': 'OpenCV H: 0..179; S,V: 0..255'},
            'sources': [{'file': item['file'], 'sha256': item['sha256']} for item in images]}, rows, overlays


def calculate(request):
    kind = request['calculation']; payload = deepcopy(request.get('parameters') or {})
    sources, rows, plot, overlays = [], None, None, []
    if kind == 'formulation':
        from highzyme.tools.formulation import calculate_recipe
        result = calculate_recipe(payload)
        result['method'] = {'name': result['method']}
        result['summary'] = {'operation': payload['operation'], **result['data']}
    elif kind == 'signal':
        from highzyme.tools.simulation import signal_analysis
        if request.get('file'):
            payload = signal_inputs(request); sources = [source_record(request['file'], request.get('source_label'))]
            if request.get('calibration_file'):
                sources.append(source_record(request['calibration_file'], request.get('calibration_label')))
        result = quantify_signal(payload) if payload['operation'] == 'quantify' else signal_analysis(payload)
        rows, plot, result['summary'] = signal_outputs(payload, result['data'])
    elif kind == 'reaction':
        from highzyme.tools.simulation import reaction_simulation
        if request.get('file'):
            sources = [source_record(request['file'], request.get('source_label'))]
            payload = json.loads(Path(request['file']).read_text(encoding='utf-8-sig'))
        result = reaction_simulation(payload)
        data = result['data']; result['summary'] = {'operation': payload['operation']}
        if 'curves' in data:
            rows = [{'label': c['label'], 'substrate_mM': x, 'initial_rate_uM_s': y}
                    for c in data['curves'] for x, y in zip(data['substrate_mM'], c['initial_rates_uM_s'])]
            plot = {'x_label': 'Substrate (mM)', 'y_label': 'Initial rate (uM/s)', 'series': [
                {'label': c['label'], 'x': data['substrate_mM'], 'y': c['initial_rates_uM_s']} for c in data['curves']]}
        else:
            rows = [{'time_s': t, **{name: values[i] for name, values in data['concentrations_M'].items()}}
                    for i, t in enumerate(data['time_s'])]
            plot = {'x_label': 'Time (s)', 'y_label': 'Concentration (M)', 'series': [
                {'label': name, 'x': data['time_s'], 'y': values} for name, values in data['concentrations_M'].items()]}
    elif kind == 'colorimetry':
        result, rows, overlays = measure_images(request)
    else:
        raise ValueError('Unknown project calculation')
    titles = {'formulation': ('配方计算', 'Formulation calculation'), 'signal': ('信号与标定分析', 'Signal analysis'),
              'reaction': ('反应动力学模拟', 'Reaction simulation'), 'colorimetry': ('图像比色', 'Image colorimetry')}
    result.update(schema='highzyme.calculation.v1', calculation=kind,
                  title=titles[kind][0 if request.get('language') == 'zh' else 1],
                  sources=result.get('sources', sources), plot=plot)
    if request.get('output_prefix'):
        # Numeric inputs are retained so signal/reaction reproduction does not reparse a changed table.
        replay = {**request, 'parameters': payload}
        if kind in ('signal', 'reaction'):
            replay.pop('file', None)
        result['files'] = export_analysis(result, replay, rows=rows)
        result['files'].update({'roi_' + str(i+1): file for i, file in enumerate(overlays)})
        if overlays:
            report = Path(result['files']['report'])
            with report.open('a', encoding='utf-8') as stream:
                stream.write('\n' + '\n\n'.join('![ROI ' + str(i+1) + '](' + Path(file).name + ')' for i, file in enumerate(overlays)) + '\n')
    return result
