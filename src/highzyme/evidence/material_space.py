"""Read-only, hash-bound material space for the UI and registered Agent tool."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import threading

from highzyme.evidence.material_features_space import (
    WEIGHTS, application_votes, digest, independent, norm,
)


class MaterialSpaceStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self.loaded_hash = None

    def _path(self, value, folder=None):
        if not isinstance(value, str):
            raise ValueError('Invalid material-space resource path')
        path = (self.root / value).resolve()
        base = self.root / folder if folder else self.root
        if not path.is_relative_to(base) or any(x in str(path).casefold() for x in ('.env', 'sealed', '封存')):
            raise ValueError('Material-space resource is outside its registered scope')
        return path

    def load(self):
        import numpy as np
        with self.lock:
            registry = json.loads((self.root / 'protocol/material-space-registry.json').read_text('utf-8'))
            if registry.get('schema') != 'highzyme.material_space.registry.v1':
                raise ValueError('Unsupported material-space registry')
            path = self._path(registry['manifest'], 'data/processed')
            if digest(path) != registry['sha256']:
                raise ValueError('Material-space manifest changed; rebuild and register the analysis')
            manifest = json.loads(path.read_text('utf-8'))
            current = json.loads((self.root / 'protocol/knowledge-registry.json').read_text('utf-8'))
            if current['active_release'] != manifest['source']['release_id']:
                raise ValueError('Material space belongs to a different database release; rebuild it first')
            from highzyme.evidence.structured_knowledge import StructuredKnowledgeStore
            store = StructuredKnowledgeStore(self.root)
            source_paths = next(iter(store._datasets().values()))
            if source_paths.get('adoption_policy') != manifest['source'].get('adoption_policy'):
                raise ValueError('Database adoption decisions changed; rebuild the material space')
            if store._verify_release(source_paths) != manifest['source']['resource_hashes']:
                raise ValueError('Database resources changed since material-space construction')
            for name, expected in manifest['files'].items():
                if Path(name).name != name or digest(path.parent / name) != expected:
                    raise ValueError('Material-space artifact changed: ' + name)
            if self.loaded_hash != registry['sha256']:
                self.manifest = manifest
                self.directory = path.parent
                self.profiles = [json.loads(line) for line in (path.parent / 'profiles.jsonl').read_text('utf-8').splitlines()]
                self.points = json.loads((path.parent / 'points.json').read_text('utf-8'))
                self.summary = json.loads((path.parent / 'summary.json').read_text('utf-8'))
                with np.load(path.parent / 'similarities.npz', allow_pickle=False) as arrays:
                    self.arrays = {key: arrays[key].copy() for key in arrays.files}
                with np.load(path.parent / 'group_similarities.npz', allow_pickle=False) as arrays:
                    self.group_arrays = {key: arrays[key].copy() for key in arrays.files}
                self.by_id = {p['material_id']: i for i, p in enumerate(self.profiles)}
                if len(self.by_id) != len(self.profiles) or len(self.points) != len(self.profiles):
                    raise ValueError('Material-space identity mapping is incomplete')
                self.loaded_hash = registry['sha256']
        return self

    def source(self):
        return {'database_release': self.manifest['source']['release_id'],
            'database_sha256': self.manifest['source']['data_sha256'],
            'analysis_release': self.manifest['release_id'], 'analysis_sha256': self.loaded_hash,
            'source_documents_read': False}

    def map(self, view='structure'):
        self.load()
        self._view(view)
        return {'status': 'AVAILABLE', 'source': self.source(), 'view': view,
            'summary': deepcopy(self.summary), 'points': [{k: deepcopy(v) for k, v in p.items() if k != 'coordinates'}
                | {'coordinates': p['coordinates'][view]} for p in self.points]}

    @staticmethod
    def _view(view):
        if view not in WEIGHTS:
            raise ValueError('View must be structure or function')

    def _select(self, request):
        if request.get('material_id'):
            if request['material_id'] not in self.by_id:
                raise ValueError('Material ID is not in the active material space')
            return self.by_id[request['material_id']]
        query = request.get('query')
        if not isinstance(query, str) or not query.strip() or len(query) > 200:
            raise ValueError('Supply material_id or a material name of at most 200 characters')
        exact, partial = [], []
        for i, p in enumerate(self.profiles):
            names = [p['material_name'], *p['aliases']]
            if any(norm(query) == norm(n) for n in names):
                exact.append(i)
            elif any(norm(query) in norm(n) for n in names):
                partial.append(i)
        matches = exact or partial
        if len(matches) != 1:
            return {'status': 'CLARIFY', 'reason': 'Choose one explicit material; names do not establish sample identity.',
                'matches': [{'material_id': self.profiles[i]['material_id'], 'material_name': self.profiles[i]['material_name']}
                            for i in matches[:20]]}
        return matches[0]

    def explanation(self, i, j, view):
        rows = []
        coverage = float(self.arrays[view + '_coverage'][i, j])
        for group, weight in WEIGHTS[view].items():
            a, b = set(self.profiles[i]['features'][group]), set(self.profiles[j]['features'][group])
            if not weight:
                continue
            similarity = float(self.group_arrays[group][i, j]) if a and b else None
            rows.append({'group': group, 'weight': weight, 'both_reported': bool(a and b),
                'group_similarity': round(similarity, 6) if similarity is not None else None,
                'score_contribution': round(weight * similarity / coverage ** .5, 6) if similarity is not None and coverage else 0,
                'shared_values': sorted(a & b)[:8], 'query_only': sorted(a - b)[:4], 'neighbor_only': sorted(b - a)[:4]})
        return rows

    def run(self, request):
        import numpy as np
        self.load()
        allowed = {'operation', 'material_id', 'query', 'view', 'limit', 'independent_only', 'target'}
        if not isinstance(request, dict) or set(request) - allowed:
            raise ValueError('Unsupported material-space request fields')
        operation, view = request.get('operation', 'neighbors'), request.get('view', 'structure')
        self._view(view)
        limit = request.get('limit', 10)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError('Material-space result limit must be 1 to 20')
        if type(request.get('independent_only', False)) is not bool:
            raise ValueError('independent_only must be boolean')
        if request.get('target') is not None and (not isinstance(request['target'], str) or len(request['target']) > 300):
            raise ValueError('Application target must be bounded text')
        if operation == 'catalog':
            data = {'materials': len(self.profiles), 'views': list(WEIGHTS), 'feature_coverage': self.summary['feature_coverage'],
                'evaluation': self.summary['evaluation'], 'candidate_materials': self.summary['candidate_materials']}
        elif operation in {'profile', 'neighbors', 'applications'}:
            selected = self._select(request)
            if isinstance(selected, dict):
                return {**selected, 'data': {}, 'source': self.source()}
            i = selected
            p = self.profiles[i]
            identity = {'material_id': p['material_id'], 'material_name': p['material_name']}
            if operation == 'profile':
                data = {**identity, 'features': deepcopy(p['features']), 'versions': deepcopy(p['versions']),
                    'applications': deepcopy(p['applications'][:limit]), 'application_count': len(p['applications']),
                    'feature_evidence': deepcopy(p['feature_evidence'][:40]),
                    'feature_evidence_count': len(p['feature_evidence']), 'issues': deepcopy(p['issues'][:20]),
                    'identity_notice': p['identity_notice']}
            elif operation == 'neighbors':
                score = self.arrays[view + '_similarity']
                eligible = [int(j) for j in np.argsort(-score[i], kind='stable') if int(j) != i and score[i, j] > 0
                    and (not request.get('independent_only') or independent(self.profiles, i, int(j)))][:limit]
                data = {**identity, 'view': view, 'neighbors': [{
                    'material_id': self.profiles[j]['material_id'], 'material_name': self.profiles[j]['material_name'],
                    'similarity': round(float(score[i, j]), 6),
                    'shared_information_fraction': round(float(self.arrays[view + '_coverage'][i, j]), 4),
                    'explanation': self.explanation(i, j, view), 'source_independent': independent(self.profiles, i, j),
                    'source': self.profiles[j]['sources'][:8]} for j in eligible]}
            else:
                score = (self.arrays['structure_similarity'] + self.arrays['function_similarity']) / 2
                proposals = application_votes(self.profiles, score, i, independent_only=True, include_known=True)
                candidates = [c for c in proposals if c['status'] == 'APPLICATION_TRANSFER_CANDIDATE']
                known_variants = [c for c in proposals if c['status'] == 'KNOWN_APPLICATION_VARIANT']
                if request.get('target'):
                    candidates = [c for c in candidates if norm(request['target']) in norm(' '.join(str(v or '') for v in c['application'].values()))]
                for c in candidates + known_variants:
                    c['supports'] = c['supports'][:5]
                data = {**identity, 'candidates': candidates[:limit], 'matching_candidates': len(candidates),
                    'known_applications': deepcopy(p['applications'][:10]),
                    'known_application_variants': known_variants[:10],
                    'reason_if_empty': None if candidates else 'No independently sourced new matching direction among the top 20 neighbors.',
                    'next_step': 'Choose a specific version and verify reaction, recognition/selectivity, readout and matched controls; do not transplant assay values.'}
        else:
            raise ValueError('Operation must be catalog, profile, neighbors or applications')
        return {'status': 'COMPLETED', 'data': data, 'source': self.source(),
            'method': 'Source-linked group TF-IDF cosine, shared-information discount; high-dimensional ranking, UMAP visualization only.',
            'limitations': ['Similarity is not a performance prediction or a calibrated success probability.',
                'Applications are transfer candidates; missing database uses do not establish novelty.',
                'Retrospective application recovery did not establish superiority over simple baselines.',
                'Reported material attributes can belong to different versions; inspect source-scoped evidence.']}


@lru_cache(maxsize=4)
def material_space_store(root):
    return MaterialSpaceStore(root)


def material_space_tool(request):
    from highzyme.infrastructure.runtime_paths import PROJECT_ROOT
    return material_space_store(PROJECT_ROOT).run(request)
