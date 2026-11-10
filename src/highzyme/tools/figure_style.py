"""Shared CNS-inspired plotting defaults for the active Highzyme scientific tools."""

COLORS = ('#3C5488', '#D96B43', '#008F7A', '#8064A2', '#4DA5C6', '#C69F35', '#6F747B', '#BA6A8C')
MARKERS = ('o', 's', '^', 'D', 'v', 'P', 'X', 'h')
LINESTYLES = ('-', '--', '-.', ':')
EXPORT_DPI = 600
ROI_BGR = (136, 84, 60)
PROFILE = {'name': 'highzyme-cns', 'single_width_mm': 89, 'double_width_mm': 180,
           'panel_height_mm': 66, 'font_pt': 8, 'tick_font_pt': 7, 'png_dpi': EXPORT_DPI, 'palette': list(COLORS)}


def figure_rc():
    return {'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'Helvetica', 'Microsoft YaHei', 'Noto Sans CJK SC', 'DejaVu Sans'],
            'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7, 'ytick.labelsize': 7,
            'legend.fontsize': 7, 'legend.frameon': False, 'legend.handlelength': 1.8,
            'axes.linewidth': .65, 'lines.linewidth': 1.15, 'lines.markersize': 3.5,
            'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': False,
            'axes.edgecolor': '#333333', 'axes.labelcolor': '#222222', 'text.color': '#222222',
            'xtick.color': '#333333', 'ytick.color': '#333333', 'xtick.major.width': .65,
            'ytick.major.width': .65, 'xtick.major.size': 3, 'ytick.major.size': 3,
            'figure.facecolor': 'white', 'axes.facecolor': 'white', 'savefig.facecolor': 'white',
            'svg.fonttype': 'none', 'pdf.fonttype': 42, 'ps.fonttype': 42, 'mathtext.fontset': 'dejavusans'}


def figure_size(columns=1, rows=1):
    return ((PROFILE['single_width_mm'] if columns == 1 else PROFILE['double_width_mm'])/25.4,
            PROFILE['panel_height_mm']*rows/25.4)


def series_style(index):
    return {'color': COLORS[index % len(COLORS)], 'marker': MARKERS[index % len(MARKERS)],
            'linestyle': LINESTYLES[index % len(LINESTYLES)]}
