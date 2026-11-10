---
name: reaction-simulation
description: Simulate supplied Michaelis-Menten parameters or a declared mass-action reaction network with local numerical integration.
---

Use `highzyme_simulate_reaction` on an authorized project JSON following [inputs.md](inputs.md). Preserve each parameter's reported, derived or assumed basis. Select a useful concentration/time grid; ask only for parameters needed by the requested model.

This skill evaluates supplied equations and parameters. For substrate concentration versus measured initial rates, use initial-rate-kinetics to estimate parameters first. The Michaelis-Menten time course models substrate depletion with constant active catalyst; do not reinterpret it as a more detailed reaction mechanism.

The tool saves numeric JSON, CSV, a report, curves and reproduction inputs. Explain the result under the declared model. Use `highzyme_replot_analysis` for presentation changes without rerunning the simulation. External computing resources are not required for these local calculations.
