"""Chemical identity and structure operations, never nanoparticle structure inference."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import urlopen

from rdkit import Chem, rdBase
from rdkit.Chem import Descriptors, rdMolDescriptors

SUBSCRIPTS = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')
GROUPS = {
    'imidazole': '[#6]1:[#6]:[#7]:[#6]:[#7]:1',
    'catechol': '[OX2H]-c1ccccc1-[OX2H]',
    'carboxylic_acid': '[CX3](=O)[OX2H]',
    'carboxylate': '[CX3](=O)[O-]',
    'primary_amine': '[NX3;H2;!$(N-C=O)]',
    'phenol': '[OX2H]-c',
}


def formula_info(formula):
    if not isinstance(formula, str) or not 1 <= len(formula) <= 200:
        raise ValueError('formula must be a bounded explicit chemical formula')
    formula = formula.translate(SUBSCRIPTS).replace(' ', '').replace('·', '.')
    table = Chem.GetPeriodicTable()
    masses = {table.GetElementSymbol(i): table.GetAtomicWeight(i) for i in range(1, 119)}
    total = {}
    for part in formula.split('.'):
        if not part:
            raise ValueError('Empty formula component')
        lead = re.match(r'^(\d+)(?=[A-Z(])', part)
        multiplier = int(lead[1]) if lead else 1
        if lead:
            part = part[len(lead[1]):]
        tokens = re.findall(r'[A-Z][a-z]?|\d+|[()]', part)
        if ''.join(tokens) != part:
            raise ValueError('Unsupported formula syntax; specify neutral formula and hydration explicitly')
        stack = [{}]
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token == '(':
                stack.append({}); index += 1; continue
            if token == ')':
                if len(stack) == 1:
                    raise ValueError('Unbalanced formula')
                atoms = stack.pop()
                if not atoms:
                    raise ValueError('Empty formula group')
            elif token in masses:
                atoms = {token: 1}
            else:
                raise ValueError('Unknown element or misplaced coefficient')
            index += 1
            count = 1
            if index < len(tokens) and tokens[index].isdigit():
                count = int(tokens[index]); index += 1
            if not 1 <= count <= 10000:
                raise ValueError('Invalid atom count')
            for key, value in atoms.items():
                stack[-1][key] = stack[-1].get(key, 0) + value * count
        if len(stack) != 1 or not stack[0] or not 1 <= multiplier <= 10000:
            raise ValueError('Invalid formula')
        for key, value in stack[0].items():
            total[key] = total.get(key, 0) + value * multiplier
    if sum(total.values()) > 100000:
        raise ValueError('Formula too large')
    return {'formula': formula, 'element_counts': total,
            'molar_mass_g_mol': sum(masses[k] * v for k, v in total.items()),
            'element_mass_fractions': {k: masses[k] * v / sum(masses[a] * b for a, b in total.items())
                                       for k, v in total.items()},
            'mass_basis': 'average atomic weights; nominal specified chemical formula',
            'structure_available': False}


def molecule_info(smiles):
    if not isinstance(smiles, str) or not 1 <= len(smiles) <= 2000:
        raise ValueError('SMILES must be text of 1..2000 characters')
    mol = Chem.MolFromSmiles(smiles)
    if mol is None or not mol.GetNumAtoms() or mol.GetNumAtoms() > 500:
        raise ValueError('Invalid or oversized molecular structure')
    if any(a.GetAtomicNum() == 0 for a in mol.GetAtoms()):
        raise ValueError('Unspecified atoms cannot define chemical identity')
    centres = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
    return {'smiles': Chem.MolToSmiles(mol, isomericSmiles=True),
            'formula': rdMolDescriptors.CalcMolFormula(mol),
            'molar_mass_g_mol': Descriptors.MolWt(mol),
            'formal_charge': Chem.GetFormalCharge(mol),
            'component_count': len(Chem.GetMolFrags(mol)),
            'stereocentres': [{'atom_index': i, 'assignment': s} for i, s in centres],
            'unspecified_stereochemistry': any(s == '?' for _, s in centres),
            'functional_groups': {name: len(mol.GetSubstructMatches(Chem.MolFromSmarts(pattern)))
                                  for name, pattern in GROUPS.items()},
            'structure_available': True}


def chemical_identity(request, fetch=None, context=None):
    if isinstance(request,dict) and set(request)=={'file_id'}:
        from highzyme.tools.nanozyme_structures import identity_from_file
        return identity_from_file(context,request['file_id'])
    if not isinstance(request, dict) or set(request) - {'name', 'cid', 'smiles', 'formula'}:
        raise ValueError('Use one of name, cid, smiles or formula')
    if len(request) != 1:
        raise ValueError('Specify exactly one chemical identity representation')
    source = {'kind': 'user_supplied_structure_or_formula'}
    if 'formula' in request:
        data = formula_info(request['formula'])
    elif 'smiles' in request:
        data = molecule_info(request['smiles'])
    else:
        key = next(iter(request)); value = request[key]
        if key == 'cid':
            if type(value) is not int or value <= 0:
                raise ValueError('CID must be a positive integer')
        elif not isinstance(value, str) or not 1 <= len(value.strip()) <= 150:
            raise ValueError('Provide a chemical name, not a document or arbitrary URL')
        if key == 'name' and str(value).strip().lower() in {'copper sulfate', 'copper sulphate', '硫酸铜'}:
            return {'status': 'CLARIFY', 'reason': 'Specify anhydrous or hydrated copper sulfate; no hydration assumed',
                    'data': {'candidates': ['CuSO4', 'CuSO4·5H2O']}}
        url = ('https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/' + key + '/' + quote(str(value), safe='')
               + '/property/MolecularFormula,MolecularWeight,IsomericSMILES/JSON')
        try:
            if fetch:
                raw = fetch(url)
            else:
                with urlopen(url, timeout=20) as response:
                    raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError('Chemical lookup response too large')
            entries = json.loads(raw)['PropertyTable']['Properties']
        except Exception as exc:
            return {'status': 'UNAVAILABLE', 'reason': 'Public identity lookup failed: ' + type(exc).__name__,
                    'data': {}, 'source': {'url': url}}
        source = {'kind': 'public_database_lookup', 'provider': 'PubChem', 'url': url,
                  'retrieved_at': datetime.now(timezone.utc).isoformat(),
                  'response_sha256': hashlib.sha256(raw).hexdigest()}
        if len(entries) != 1:
            return {'status': 'CLARIFY', 'reason': 'Multiple identities; select an explicit CID',
                    'data': {'candidates': entries[:5]}, 'source': source}
        row = entries[0]
        source['property_snapshot'] = row
        data = molecule_info(row.get('SMILES', row.get('IsomericSMILES', '')))
        data.update(cid=row['CID'], database_formula=row['MolecularFormula'],
                    database_molar_mass_g_mol=float(row['MolecularWeight']))
        source['url'] = 'https://pubchem.ncbi.nlm.nih.gov/compound/' + str(row['CID'])
        source['query_url'] = url
    limitations = ['Chemical identity/structure only; no prediction of nanozyme morphology, binding or activity.',
                  'Nominal chemical form must match the reagent used; purity and product composition are not inferred.']
    if 'formula' in request:
        limitations.append('A formula does not resolve connectivity, stereochemistry, oxidation state or polymorph.')
    if data.get('unspecified_stereochemistry'):
        limitations.append('Stereochemistry is unspecified; no L/D identity has been assigned.')
    return {'status': 'COMPLETED', 'data': data, 'source': source,
            'method': 'RDKit ' + rdBase.rdkitVersion + ' and explicit chemical representation',
            'limitations': limitations}
