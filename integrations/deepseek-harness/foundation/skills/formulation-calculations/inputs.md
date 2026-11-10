Each quantity is `{"value": 1, "unit": "mM"}`. Parameters include `operation` and the fields below.

| operation | required inputs | optional inputs |
|---|---|---|
| convert | quantity, to_unit | |
| mass_to_amount | mass; formula OR molar_mass | purity_fraction |
| amount_to_mass | amount; formula OR molar_mass | purity_fraction |
| prepare_solution | concentration, final_volume; formula OR molar_mass | purity_fraction |
| dilution | stock_concentration, target_concentration | final_volume |
| mixture | stocks, final_volume | |
| ratio | amounts | |

Examples:

```json
{"operation":"prepare_solution","formula":"CuSO4.5H2O","concentration":{"value":10,"unit":"mM"},"final_volume":{"value":100,"unit":"mL"}}
```

Use the formula parser's actual supported hydrate notation; preserve the entered reagent identity. An explicit molar mass is an alternative when the representation is unsupported.

```json
{"operation":"dilution","stock_concentration":{"value":10,"unit":"mM"},"target_concentration":{"value":1,"unit":"mM"},"final_volume":{"value":10,"unit":"mL"}}
```

```json
{"operation":"mixture","stocks":[{"concentration":{"value":10,"unit":"mM"},"volume":{"value":100,"unit":"uL"}}],"final_volume":{"value":1,"unit":"mL"}}
```

Each mixture stock accepts concentration and volume quantities plus an optional descriptive label; the label does not change solute identity. Do not add other fields.

Mixture aliquots must refer to the same solute and concentration basis. Ratios use `amounts: [{"label":"A","quantity":{"value":1,"unit":"mmol"}},{"label":"B","quantity":{"value":2,"unit":"mmol"}}]`. Purity is a fraction in (0,1].
