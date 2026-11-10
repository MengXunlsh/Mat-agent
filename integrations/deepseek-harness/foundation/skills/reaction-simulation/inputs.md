Michaelis-Menten parameters use mM for Km/substrate and uM/s for Vmax:

```json
{"operation":"michaelis_menten","curves":[{"label":"sample-a","km_mM":0.3,"vmax_uM_s":2.4,"source":"a fitted project result"}],"substrate_mM":[0,0.05,0.1,0.2,0.4,0.8,1.6],"time_s":120}
```

`time_s` is optional. Reciprocal-plot conversion uses operation `reciprocal_parameters`; each curve supplies `label`, `slope`, `intercept`, `x_scale_per_M`, `y_scale_s_per_M` and `source`. These scales describe the actual plotted axes; do not assume them from an unlabeled figure.

Declared mass-action networks use initial concentrations in M, time in seconds and k in M^(1-reaction order)/s:

```json
{"operation":"network","species":{"A":0.001,"B":0},"reactions":[{"reactants":{"A":1},"products":{"B":1},"k":0.1,"parameter_basis":"assumed"}],"duration_s":30,"points":65}
```

Each k basis is `reported`, `derived` or `assumed`. Species identifiers only name model variables. Stoichiometry and rate laws are the declared model; they do not establish a chemical mechanism.
