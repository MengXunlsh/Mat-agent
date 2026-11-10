"""Unit-aware nominal formulation arithmetic. No inferred preparation conditions."""
from __future__ import annotations

import math
import pint
from highzyme.tools.chemistry import formula_info

UNITS = pint.UnitRegistry()
ALIASES = {'M': 'mol/liter', 'mM': 'mmol/liter', 'uM': 'micromol/liter',
           'µM': 'micromol/liter', 'μM': 'micromol/liter', 'nM': 'nanomol/liter',
           'μL': 'microliter', 'µL': 'microliter', 'uL': 'microliter',
           'μg': 'microgram', 'µg': 'microgram', 'ug': 'microgram',
           '°C': 'degC', 'C': 'degC'}


def number(value, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError('Expected a finite' + (' positive' if positive else '') + ' number')
    return value


def unit(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 80:
        raise ValueError('Unit must be explicit')
    return ALIASES.get(value, value.replace('μ', 'u').replace('µ', 'u'))


def quantity(item, target=None, *, positive=False):
    if not isinstance(item, dict) or set(item) != {'value', 'unit'}:
        raise ValueError('Quantity requires exactly value and unit')
    q = UNITS.Quantity(number(item['value'], positive=positive), unit(item['unit']))
    return q.to(unit(target)) if target else q


def output(q, target):
    value = float(q.to(unit(target)).magnitude)
    number(value)
    return {'value': value, 'unit': target}


def calculate_recipe(request):
    if not isinstance(request, dict):
        raise ValueError('Request must be an object')
    op = request.get('operation')
    schemas = {
        'convert': ({'quantity', 'to_unit'}, set()),
        'mass_to_amount': ({'mass'}, {'formula', 'molar_mass', 'purity_fraction'}),
        'amount_to_mass': ({'amount'}, {'formula', 'molar_mass', 'purity_fraction'}),
        'prepare_solution': ({'concentration', 'final_volume'}, {'formula', 'molar_mass', 'purity_fraction'}),
        'dilution': ({'stock_concentration', 'target_concentration'}, {'final_volume'}),
        'mixture': ({'stocks', 'final_volume'}, set()),
        'ratio': ({'amounts'}, set()),
    }
    if op not in schemas:
        raise ValueError('Unknown recipe operation')
    required, optional = schemas[op]
    if not required <= set(request) or set(request) - required - optional - {'operation'}:
        raise ValueError('Missing or unsupported fields for ' + op)
    notes = ['Nominal calculation from declared inputs; no experimental yield or final material composition inferred.']
    data = {}
    if op == 'convert':
        data['converted'] = output(quantity(request['quantity']), request['to_unit'])
    elif op in {'mass_to_amount', 'amount_to_mass', 'prepare_solution'}:
        if ('formula' in request) == ('molar_mass' in request):
            raise ValueError('Specify exactly one explicit formula or molar_mass')
        mw = (UNITS.Quantity(formula_info(request['formula'])['molar_mass_g_mol'], 'g/mol')
              if 'formula' in request else quantity(request['molar_mass'], 'g/mol', positive=True))
        purity = number(request.get('purity_fraction', 1), positive=True)
        if purity > 1:
            raise ValueError('Purity must be a fraction in (0,1]')
        notes.append('Purity is explicitly supplied.' if 'purity_fraction' in request else 'No purity correction; pure-entity nominal basis.')
        data.update(molar_mass=output(mw, 'g/mol'), purity_fraction=purity,
                    amount_basis='Formula units of ' + request['formula'] if 'formula' in request else 'Chemical entity represented by supplied molar_mass; not automatically element equivalents')
        if op == 'mass_to_amount':
            data['amount'] = output(quantity(request['mass'], 'g', positive=True) * purity / mw, 'umol')
        elif op == 'amount_to_mass':
            amount = quantity(request['amount'], 'mol', positive=True)
            data.update(amount=output(amount, 'umol'), mass=output(amount * mw / purity, 'mg'))
        else:
            amount = quantity(request['concentration'], 'mol/liter', positive=True) * quantity(request['final_volume'], 'liter', positive=True)
            data.update(amount=output(amount, 'umol'), mass=output(amount * mw / purity, 'mg'))
    elif op == 'dilution':
        stock = quantity(request['stock_concentration'], positive=True)
        target = quantity(request['target_concentration'], positive=True).to(stock.units)
        if not (stock.check('[substance] / [length] ** 3') or stock.check('[mass] / [length] ** 3')):
            raise ValueError('Dilution requires molar or mass concentration')
        if target > stock:
            raise ValueError('Dilution cannot produce a concentration higher than the stock')
        if 'final_volume' in request:
            vol = quantity(request['final_volume'], 'mL', positive=True)
            data.update(stock_volume=output(target / stock * vol, 'uL'), final_volume=output(vol, 'mL'))
            notes.append('Make up to final volume; solvent volumes are not assumed additive.')
        else:
            data.update(dilution_feasible=True, required_stock_fraction=float((target / stock).to('').magnitude))
            notes.append('Concentration feasibility only. Final volume is missing; no aliquot volume is calculated or inferred.')
    elif op == 'mixture':
        stocks = request['stocks']
        if not isinstance(stocks, list) or not 1 <= len(stocks) <= 30:
            raise ValueError('Supply 1..30 aliquots of the SAME solute')
        vol = quantity(request['final_volume'], 'mL', positive=True)
        added = UNITS.Quantity(0, 'mL'); total = None; basis = None
        for index, s in enumerate(stocks):
            if not isinstance(s, dict) or not {'concentration', 'volume'} <= s.keys():
                raise ValueError(f'stocks[{index}] requires concentration and volume, each as {{value, unit}}')
            extra = s.keys() - {'concentration', 'volume', 'label'}
            if extra:
                raise ValueError(f'stocks[{index}] has unsupported fields: {", ".join(sorted(extra))}; use concentration, volume and optional label')
            c = quantity(s['concentration'], positive=True)
            v = quantity(s['volume'], 'mL', positive=True)
            if not (c.check('[substance] / [length] ** 3') or c.check('[mass] / [length] ** 3')):
                raise ValueError('Mixture requires mass or molar concentrations')
            if basis is None:
                basis = 'uM' if c.check('[substance] / [length] ** 3') else 'mg/mL'
            term = c * v; total = term if total is None else total + term; added += v
        if added > vol:
            raise ValueError('Aliquot volumes exceed declared final volume')
        data['final_concentration'] = output(total / vol, basis)
        notes.append('Aliquots must refer to the same solute and concentration basis; identities are not inferred.')
    else:
        values = request['amounts']
        if not isinstance(values, list) or not 2 <= len(values) <= 30:
            raise ValueError('Supply 2..30 labelled amounts')
        if any(not isinstance(v, dict) or set(v) != {'label', 'quantity'} or not isinstance(v['label'], str) for v in values):
            raise ValueError('Each amount requires label and quantity')
        if len({v['label'] for v in values}) != len(values):
            raise ValueError('Amount labels must be distinct')
        quantities = [quantity(v['quantity'], positive=True) for v in values]
        for q in quantities:
            if not (q.check('[substance]') or q.check('[mass]')):
                raise ValueError('Ratios require masses or substance amounts')
        data['relative_to_first'] = {v['label']: float((q / quantities[0]).to('').magnitude)
                                     for v, q in zip(values, quantities)}
        data['ratio_basis'] = 'molar' if quantities[0].check('[substance]') else 'mass'
    return {'status': 'COMPLETED', 'data': data, 'method': 'Pint dimensional arithmetic: ' + op,
            'source': {'kind': 'declared_input'}, 'limitations': notes}
