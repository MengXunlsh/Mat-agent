"""Source-linked material profiles, independent of application labels.

This is an analysis projection of the current release, never a database repair.
Profiles collect reported version attributes; they do not describe one sample
possessing every attribute. Experimental numeric results are not ranking inputs.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
import unicodedata

from highzyme.evidence.knowledge_adoption import load_adoption_policy

GROUPS = ('class', 'elements', 'components', 'morphology', 'surface', 'phase', 'activity', 'reactants')
WEIGHTS = {
    'structure': dict(zip(GROUPS, (.10, .28, .24, .12, .18, .08, 0, 0))),
    'function': dict(zip(GROUPS, (.05, .12, .10, .05, .08, 0, .35, .25))),
}
FEATURE_GROUP = {'material_class': 'class', 'composition': 'components',
                 'chemical_formula': 'components', 'morphology': 'morphology',
                 'surface_modification': 'surface', 'carrier_or_backbone': 'components',
                 'crystal_phase': 'phase'}
ELEMENTS = set(('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn '
    'Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd '
    'Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th '
    'Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og').split())
BOILERPLATE = re.compile(r'\b(?:source[- ]reported|reported|material component of the|'
    r'nanoparticles?|nanomaterials?|materials?|unknown|not reported|unspecified)\b', re.I)
IDENTITY_NOTICE = 'Reported attributes may belong to different versions; inspect scoped evidence before specifying a sample.'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def norm(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(value))).strip().casefold()


def source_key(url):
    text = str(url).strip().removeprefix('https://doi.org/').removeprefix('http://doi.org/')
    match = re.search(r'10\.\d{4,9}/[^\s?#]+', text, re.I)
    if match:
        # SI and article share one study, rather than independent evidence votes.
        return re.sub(r'\.s\d+$', '', match.group().rstrip('/.,;')).casefold()
    return str(url).strip().rstrip('/').casefold()


def strings(value):
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [x for item in value for x in strings(item)]
    if isinstance(value, dict):
        if 'value' in value:
            return strings(value['value'])
        return [x for k, v in value.items() if k not in {'source', 'sources', 'basis', 'unit', 'context'}
                for x in ([k] if v is None and k not in {'overall'} else strings(v))]
    return []


def component_values(value):
    if isinstance(value, dict) and isinstance(value.get('components'), dict):
        return list(value['components'])
    return strings(value)


def formula_elements(formula):
    text = unicodedata.normalize('NFKC', str(formula)).strip()
    if not re.fullmatch(r'[A-Za-z0-9().·+\-]+', text):
        return []
    symbols = re.findall(r'[A-Z][a-z]?', text)
    residue = re.sub(r'[A-Z][a-z]?|[0-9().·+\-]', '', text)
    return sorted(set(symbols)) if symbols and not residue and set(symbols) <= ELEMENTS else []


def profile_material(material, decisions=()):
    ident = material['material_id']
    profile = {'material_id': ident, 'material_name': material.get('material_name') or ident,
        'aliases': material.get('aliases', []), 'features': {g: [] for g in GROUPS},
        'feature_evidence': [], 'applications': [], 'versions': [], 'sources': [], 'issues': [],
        'identity_notice': IDENTITY_NOTICE}
    feature_sets = {g: set() for g in GROUPS}
    seen_evidence, seen_apps = set(), set()

    def permitted(path, version_id):
        for decision in decisions:
            if decision['kind'] == 'sample_identity' and decision.get('target_id') == version_id:
                return False
            target = decision.get('path')
            if target and (path == target or path.startswith(target + '/')):
                return False
        return True

    def evidence(group, values, obs, path, version_id, record_id):
        if not permitted(path, version_id):
            profile['issues'].append({'path': path, 'reason': 'Existing ABANDON decision; retained outside analysis.'})
            return
        values = [s.strip() for s in values if isinstance(s, str) and s.strip()]
        if not values:
            return
        source = obs.get('source', []) if isinstance(obs, dict) else []
        if isinstance(source, str):
            source = [source]
        if not source:
            profile['issues'].append({'path': path, 'reason': 'No explicit source for the reported feature.'})
            return
        # Preserve case in explicitly reported formulae and element symbols.
        # Co and CO are different chemical identities, although prose is folded.
        feature_sets[group].update(unicodedata.normalize('NFKC', s).strip()
            if group == 'elements' or (group == 'components' and
                ('/chemical_formula/' in path or formula_elements(s))) else norm(s) for s in values)
        key = (group, path)
        if key not in seen_evidence:
            seen_evidence.add(key)
            profile['feature_evidence'].append({'group': group, 'values': values, 'source': source,
                'version_id': version_id, 'record_id': record_id, 'path': path})
        profile['sources'].extend(source)

    def block(obj, path, version_id=None, record_id=None):
        for field, group in FEATURE_GROUP.items():
            for i, obs in enumerate((obj.get('material_features') or {}).get(field) or []):
                loc = f'{path}/material_features/{field}/{i}'
                val = obs.get('value')
                values = component_values(val) if field == 'composition' else strings(val)
                evidence(group, values, obs, loc, version_id, record_id)
                if field in {'chemical_formula', 'composition'}:
                    evidence('elements', [el for s in values for el in formula_elements(s)], obs, loc, version_id, record_id)
        apps = (obj.get('application_information') or {}).get('applications') or []
        for i, obs in enumerate(apps):
            loc = f'{path}/application_information/applications/{i}'
            if not permitted(loc, version_id):
                continue
            value = obs.get('value', {})
            if not isinstance(value, dict):
                continue
            levels = [value.get(k) for k in ('major_category', 'subcategory', 'direction')]
            sources = obs.get('source', [])
            if isinstance(sources, str):
                sources = [sources]
            if not any(levels) or not sources:
                continue
            key = tuple(norm(x or '') for x in levels) + (version_id, record_id)
            if key in seen_apps:
                continue
            seen_apps.add(key)
            profile['applications'].append({'major_category': levels[0], 'subcategory': levels[1],
                'direction': levels[2], 'source': sources, 'version_id': version_id,
                'record_id': record_id, 'path': loc})
            profile['sources'].extend(sources)
        conditions = obj.get('reaction_conditions') or {}
        activity = conditions.get('activity_type')
        if isinstance(activity, dict):
            evidence('activity', strings(activity), activity, f'{path}/reaction_conditions/activity_type', version_id, record_id)
        for i, stage in enumerate(conditions.get('stages', [])):
            for j, component in enumerate(stage.get('components', [])):
                if component.get('role') in {'substrate', 'co_substrate'} and component.get('substance'):
                    evidence('reactants', [component['substance']], component,
                        f'{path}/reaction_conditions/stages/{i}/components/{j}', version_id, record_id)

    block(material, '')
    for i, version in enumerate(material.get('variants', [])):
        vid = version['version_id']
        allowed = not any(d['kind'] == 'sample_identity' and d.get('target_id') == vid for d in decisions)
        profile['versions'].append({'version_id': vid, 'version_name': version.get('version_name'),
            'record_count': len(version.get('records', [])), 'analysis_eligible': allowed})
        if not allowed:
            profile['issues'].append({'version_id': vid, 'reason': 'Sample identity abandoned in current release decisions.'})
            continue
        block(version, f'/variants/{i}', vid)
        for j, record in enumerate(version.get('records', [])):
            block(record, f'/variants/{i}/records/{j}', vid, record['record_id'])
    for i, record in enumerate(material.get('material_information_records', [])):
        block(record, f'/material_information_records/{i}', None, record['record_id'])
    profile['features'] = {g: sorted(feature_sets[g]) for g in GROUPS}
    profile['sources'] = sorted(set(profile['sources']))
    profile['study_keys'] = sorted({source_key(s) for s in profile['sources'] if source_key(s).startswith('10.')})
    profile['known_groups'] = [g for g in GROUPS if profile['features'][g]]
    if not profile['known_groups']:
        profile['issues'].append({'reason': 'No sourced usable similarity features; displayed as insufficient information.'})
    return profile


def load_profiles(root):
    from highzyme.evidence.structured_knowledge import StructuredKnowledgeStore
    store = StructuredKnowledgeStore(root)
    paths = next(iter(store._datasets().values()))
    hashes = store._verify_release(paths)
    policy = load_adoption_policy(root, paths.get('adoption_policy'), hashes['data'])
    with paths['data'].open(encoding='utf-8-sig') as stream:
        profiles = [profile_material(json.loads(line), policy.get(json.loads(line)['material_id'], [])) for line in stream]
    if digest(paths['data']) != hashes['data']:
        raise ValueError('Database changed during profile construction')
    return profiles, {'release_id': paths['release_id'], 'data': str(paths['data'].relative_to(root)),
        'data_sha256': hashes['data'], 'resource_hashes': hashes,
        'adoption_policy': paths.get('adoption_policy')}


def matrices(profiles):
    import numpy as np
    from scipy import sparse
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize
    parts, present, vocabulary = {}, {}, {}
    for group in GROUPS:
        docs = [' '.join(BOILERPLATE.sub(' ', s) for s in p['features'][group]) for p in profiles]
        if any(d.strip() for d in docs):
            vectorizer = TfidfVectorizer(lowercase=group not in {'elements', 'components'}, token_pattern=r'(?u)\b[\w][\w.+-]*\b',
                ngram_range=(1, 2) if group in {'morphology', 'surface', 'components'} else (1, 1),
                sublinear_tf=True, max_features=5000)
            x = vectorizer.fit_transform(docs)
            vocabulary[group] = vectorizer.get_feature_names_out().tolist()
        else:
            x = sparse.csr_matrix((len(profiles), 0))
            vocabulary[group] = []
        parts[group] = x
        present[group] = np.asarray(x.getnnz(axis=1) > 0)
    results = {}
    for view, weights in WEIGHTS.items():
        numerator = np.zeros((len(profiles), len(profiles)), dtype=np.float64)
        coverage = numerator.copy()
        blocks = []
        for group, weight in weights.items():
            if not weight:
                continue
            numerator += weight * (parts[group] @ parts[group].T).toarray()
            coverage += weight * np.outer(present[group], present[group])
            blocks.append(parts[group] * weight ** .5)
        # Shared-field cosine average, discounted by the shared information fraction.
        score = np.divide(numerator, np.sqrt(coverage), out=np.zeros_like(numerator), where=coverage > 0)
        np.clip(score, 0, 1, out=score)
        np.fill_diagonal(score, 1)
        results[view] = {'similarity': score.astype('float32'), 'coverage': coverage.astype('float32'),
                         'features': normalize(sparse.hstack(blocks).tocsr())}
    return results, parts, vocabulary


def labels(profile, level='subcategory'):
    result = {}
    for app in profile['applications']:
        value = app.get(level)
        if value:
            key = norm(value)
            result.setdefault(key, {'label': value, 'sources': set()})['sources'].update(source_key(s) for s in app['source'])
    return result


def independent(profiles, i, j):
    return (i != j and norm(profiles[i]['material_name']) != norm(profiles[j]['material_name'])
            and not set(profiles[i]['study_keys']) & set(profiles[j]['study_keys']))


def application_identity(application):
    """Conservatively identify an already reported analyte, independent of readout.

    Recognition/readout/context differences remain preserved as known-use variants,
    not evidence that the analyte has never been investigated for this material.
    """
    direction = norm(application.get('direction') or '')
    match = re.search(r'\b(?:detection|sensing|determination|monitoring)\s+(?:of\s+|for\s+)?(.+)', direction)
    if match:
        target = re.split(r'\s+(?:based on|using|via|with|through|in|by)\s+', match.group(1))[0]
        target = re.sub(r'\s*\([^)]*\)', '', target).strip(' .,:;')
        if target:
            return ('reported_analyte', target)
    match = re.search(r'\bfor\s+(.+?)\s+(?:detection|sensing|determination)$', direction)
    if match:
        return ('reported_analyte', match.group(1).strip(' .,:;'))
    return ('reported_direction', direction)


def application_votes(profiles, scores, target, *, top_neighbors=20, independent_only=False, include_known=False):
    import numpy as np
    candidates = [int(j) for j in np.argsort(-scores[target], kind='stable') if j != target
        and scores[target, j] > 0 and (not independent_only or independent(profiles, target, int(j)))][:top_neighbors]
    votes = {}
    for j in candidates:
        unique = {}
        for app in profiles[j]['applications']:
            if not app.get('direction'):
                continue
            key = tuple(norm(app.get(k) or '') for k in ('major_category', 'subcategory', 'direction'))
            unique.setdefault(key, app)
        for key, app in unique.items():
            entry = votes.setdefault(key, {'application': {k: app.get(k) for k in ('major_category', 'subcategory', 'direction')},
                'score': 0., 'supports': [], 'study_keys': set()})
            # One weight per independent source, rather than one per duplicated record.
            studies = {source_key(s) for s in app['source']}
            fresh = studies - entry['study_keys']
            if fresh:
                entry['score'] += float(scores[target, j])
                entry['study_keys'].update(fresh)
            entry['supports'].append({'material_id': profiles[j]['material_id'],
                'material_name': profiles[j]['material_name'], 'similarity': round(float(scores[target, j]), 5),
                'source': app['source'], 'version_id': app['version_id'],
                'record_id': app['record_id'], 'path': app['path']})
    known = {tuple(norm(a.get(k) or '') for k in ('major_category', 'subcategory', 'direction')) for a in profiles[target]['applications']}
    known_identities = {application_identity(a) for a in profiles[target]['applications'] if a.get('direction')}
    output = []
    for key, value in sorted(votes.items(), key=lambda pair: (-pair[1]['score'], pair[0])):
        known_use = key in known or application_identity(value['application']) in known_identities
        if known_use and not include_known:
            continue
        value['independent_sources'] = len(value.pop('study_keys'))
        value['score'] = round(value['score'], 6)
        value['status'] = 'KNOWN_APPLICATION_VARIANT' if known_use else 'APPLICATION_TRANSFER_CANDIDATE'
        output.append(value)
    return output


def evaluate(profiles, scores, top_k=3):
    """Transductive label holdout; no application text is used to construct scores.

    All labels of each query are hidden. Evidence neighbors sharing a study or
    a normalized material name are excluded. Missing labels are not negatives.
    """
    import numpy as np
    rows, skipped = [], []
    truths = [set(labels(p)) for p in profiles]
    for i, profile in enumerate(profiles):
        if not truths[i]:
            skipped.append({'material_id': profile['material_id'], 'reason': 'No sourced subcategory labels for holdout.'})
            continue
        allowed = [j for j in range(len(profiles)) if independent(profiles, i, j) and truths[j]]
        if not allowed:
            skipped.append({'material_id': profile['material_id'], 'reason': 'No independent labelled reference materials.'})
            continue
        ranked = sorted(allowed, key=lambda j: (-float(scores[i, j]), j))
        votes = Counter()
        seen_sources = {}
        for j in ranked[:20]:
            if scores[i, j] > 0:
                for label, info in labels(profiles[j]).items():
                    fresh = info['sources'] - seen_sources.setdefault(label, set())
                    if fresh:
                        votes[label] += float(scores[i, j])
                        seen_sources[label].update(fresh)
        same_class = set(profile['features']['class'])
        class_votes, global_votes = Counter(), Counter()
        for j in allowed:
            global_votes.update(truths[j])
            if same_class & set(profiles[j]['features']['class']):
                class_votes.update(truths[j])
        methods = {'neighbors': votes, 'same_class': class_votes, 'popularity': global_votes}
        metrics = {}
        for method, counter in methods.items():
            selected = [key for key, _ in sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:top_k]]
            matched = truths[i] & set(selected)
            metrics[method] = {'hit': int(bool(matched)), 'recall': len(matched) / len(truths[i]), 'predicted': selected}
        rows.append({'material_id': profile['material_id'], 'classes': sorted(same_class),
            'truth': sorted(truths[i]), 'independent_reference_count': len(allowed), 'metrics': metrics})
    summary = {m: {'hit_at_3': float(np.mean([r['metrics'][m]['hit'] for r in rows])) if rows else None,
                  'recall_at_3': float(np.mean([r['metrics'][m]['recall'] for r in rows])) if rows else None}
               for m in ('neighbors', 'same_class', 'popularity')}
    by_class = {}
    for category in sorted({c for row in rows for c in row['classes']}):
        subset = [r for r in rows if category in r['classes']]
        by_class[category] = {'materials': len(subset), 'metrics': {m: {
            'hit_at_3': float(np.mean([r['metrics'][m]['hit'] for r in subset])),
            'recall_at_3': float(np.mean([r['metrics'][m]['recall'] for r in subset]))}
            for m in summary}}
    return {'protocol': 'transductive_application_label_holdout_with_source_and_name_exclusion_v1',
        'level': 'subcategory', 'top_k': top_k, 'evaluated_materials': len(rows), 'skipped_materials': len(skipped),
        'metrics': summary, 'by_class': by_class, 'rows': rows, 'skipped': skipped,
        'limitations': ['Retrospective label recovery, not prospective discovery or experimental validation.',
            'No application labels/text enter similarity. Unlabelled features are transductively available.',
            'Vocabulary/IDF use the unlabelled full corpus; this is not a strict inductive unseen-corpus test.',
            'Unknown applications are not negative labels; source exclusion does not remove every possible secondary citation.']}
