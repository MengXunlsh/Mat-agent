"""Shared files and plotting for local research calculations."""
import csv
import json
from pathlib import Path
from highzyme.tools.figure_style import figure_rc, figure_size, series_style, EXPORT_DPI, PROFILE


def plot_analysis(result, prefix, options=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    options = options or {}
    plot = result['plot']
    series = plot['series']
    labels = options.get('labels', [s['label'] for s in series])
    if len(labels) != len(series) or any(not isinstance(label, str) or not label.strip() for label in labels):
        raise ValueError('Supply one nonempty label per plotted series')
    with plt.rc_context(figure_rc()):
        fig, ax = plt.subplots(figsize=figure_size(), layout='constrained')
        for i, (item, label) in enumerate(zip(series, labels)):
            style = series_style(i)
            if item.get('style') == 'points':
                ax.scatter(item['x'], item['y'], s=16, c=style['color'], marker=style['marker'], edgecolors='white', linewidths=.4, label=label, zorder=3)
            else:
                ax.plot(item['x'], item['y'], color=style['color'], linestyle=style['linestyle'], label=label)
        ax.set(xlabel=options.get('x_label', plot['x_label']), ylabel=options.get('y_label', plot['y_label']))
        ax.legend()
        files = {}
        for fmt in ('png', 'svg'):
            file = Path(str(prefix) + '-curve.' + fmt)
            fig.savefig(file, dpi=EXPORT_DPI)
            files[fmt] = str(file)
        plt.close(fig)
    return files


def export_analysis(result, request, *, rows=None):
    prefix = Path(request['output_prefix'])
    prefix.parent.mkdir(parents=True, exist_ok=True)
    files = {key: str(prefix) + suffix for key, suffix in {
        'result': '-result.json', 'request': '-input.json', 'report': '-report.md', 'script': '-reproduce.py'}.items()}
    if result.get('plot'):
        result['plot']['profile'] = PROFILE
    Path(files['result']).write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    Path(files['request']).write_text(json.dumps({k: v for k, v in request.items() if k != 'output_prefix'}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    zh = request.get('language') == 'zh'
    report = ['# ' + result['title'], '', ('方法：' if zh else 'Method: ') + result['method']['name'], '']
    if result.get('plot'):
        report += ['![Analysis curve](' + prefix.name + '-curve.svg)', '']
    for key, value in result.get('summary', {}).items():
        report.append('- ' + key + ': ' + str(value))
    for source in result.get('sources', []):
        report += ['', ('来源：' if zh else 'Source: ') + source['file'] + ' · SHA-256 ' + source['sha256']]
    if rows:
        files['table'] = str(prefix) + '-data.csv'
        with Path(files['table']).open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        headers = list(rows[0])
        cell = lambda value: str(value).replace('|', '\\|').replace('\n', ' ')
        report += ['', '| ' + ' | '.join(headers) + ' |', '|' + '---|' * len(headers)]
        report += ['| ' + ' | '.join(cell(row[h]) for h in headers) + ' |' for row in rows[:20]]
        if len(rows) > 20:
            report += ['', ('完整数据见 CSV。' if zh else 'The CSV contains the complete data.')]
    report += ['', ('完整输入与数值结果见同目录 JSON。' if zh else 'Complete inputs and numerical results are saved in the adjacent JSON files.')]
    Path(files['report']).write_text('\n'.join(report) + '\n', encoding='utf-8')
    Path(files['script']).write_text(
        '"""Reproduce this calculation in the installed Highzyme environment."""\n'
        'import json\nfrom pathlib import Path\nimport sys\nfrom highzyme.foundation_science import run\n'
        'file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name(' + repr(Path(files['request']).name) + ')\n'
        'request = json.loads(file.read_text(encoding="utf-8"))\nrequest.pop("output_prefix", None)\n'
        'print(json.dumps(run(request), ensure_ascii=True, allow_nan=False))\n', encoding='utf-8')
    if result.get('plot'):
        files.update(plot_analysis(result, prefix))
    return files


def replot_analysis(request):
    file = Path(request['file'])
    if file.stat().st_size > 32 * 1024**2:
        raise ValueError('Saved analysis exceeds 32 MiB')
    result = json.loads(file.read_text(encoding='utf-8-sig'))
    if result.get('schema') != 'highzyme.calculation.v1' or not result.get('plot'):
        raise ValueError('Select a saved Highzyme calculation with a plot')
    prefix = Path(request['output_prefix']); prefix.parent.mkdir(parents=True, exist_ok=True)
    options = {k: request[k] for k in ('labels', 'x_label', 'y_label') if k in request}
    files = plot_analysis(result, prefix, options)
    files['options'] = str(prefix) + '-plot.json'
    Path(files['options']).write_text(json.dumps({**options, 'profile': PROFILE}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'refitted': False, 'files': files}
