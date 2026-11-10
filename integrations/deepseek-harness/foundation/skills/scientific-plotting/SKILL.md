---
name: scientific-plotting
description: Plot supplied research data or restyle existing analysis outputs with mat-agent's shared CNS-inspired palette, typography and editable exports.
---

Prefer the existing fit/replot tools for their supported results. A visual change to a saved fit or simulation uses replotting, not a new fit. For custom charts, inspect the data and the user's scientific question, then reuse the shared style below in authorized code execution.

The `scientificRuntime.python` from `highzyme_project_context` is the installed mat-agent scientific environment. It provides Matplotlib and `highzyme.tools.figure_style`. Respect the project's execution permission and a user-selected environment.

```python
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from highzyme.tools.figure_style import figure_rc, figure_size, series_style, EXPORT_DPI

with plt.rc_context(figure_rc()):
    fig, ax = plt.subplots(figsize=figure_size(), layout='constrained')
    # Supply the actual data, axis labels, units and appropriate series styles here.
    for fmt in ('svg', 'png'):
        fig.savefig(output_prefix + '.' + fmt, dpi=EXPORT_DPI)
    plt.close(fig)
```

The profile uses a white background, restrained blue/orange/teal/purple categorical colors, Arial/Helvetica-compatible type, thin axes, distinct markers/line styles, editable SVG text and 600 dpi PNG. Default single-panel width is 89 mm; two-column panels use 180 mm. These are mat-agent's plotting defaults; a specified target journal or user layout takes precedence.

Use color consistently for the same scientific category and add markers/line styles where needed. Use a sequential color map for ordered quantities and a diverging map only for a meaningful midpoint. Preserve raw image pixels; ROI marks belong in a separate annotated output. Do not add decorative titles, gradients, invented error bars or significance marks.

Typeset variables, subscripts, superscripts, chemical formulas and units as scientific notation, not literal code identifiers. For example, render E_ref as a mathematical subscript and label conv_thr as the SCF tolerance. Use Matplotlib math text in exports and corresponding formatted labels in interactive previews; inspect both.

Keep source data and numerical results unchanged when restyling. Save plotting code/options with the output and inspect the actual export at its intended size. Built-in replot tools update the existing analysis artifact and do not create a second figure-only artifact. For custom charts, publish the main report/figure and supporting data, code and graphics together with highzyme_artifact_save, using related_files and files. Revisions use artifact_id, the same paths and project Git; an independent chart uses separate paths.
