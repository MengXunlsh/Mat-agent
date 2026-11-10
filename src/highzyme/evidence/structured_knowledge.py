"""Read-only, source-bounded access to reported material/assay records.

Search results are discovery metadata, never evidence that a source was read.
Reading preserves raw observations, their scope and source roles; it neither
normalizes numbers nor dereferences historical/permission-restricted paths.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import threading
import unicodedata
from .assay_projection import ASSAY_SCHEMA, APPLICATION_SCHEMA, SEARCH_ALIASES, project_record, record_pointer
from .entity_projection import ENTITY_SCHEMA, project_entities
from .knowledge_adoption import load_adoption_policy, annotate_adoption
from . import knowledge_query

DEFAULT_ENTRY = "protocol/knowledge-registry.json"
SCHEMA = "highzyme.material.reported.parallel.v2"
MATERIAL_FEATURE_SCHEMA = "highzyme.material.features.english.v1"
GROUPS = ("material_features", "application_information", "reaction_conditions", "reported_results")
ACTIVITIES = {
    "pod": "peroxidase", "过氧化物酶": "peroxidase", "peroxidase-like": "peroxidase",
    "oxd": "oxidase", "氧化酶": "oxidase", "oxidase-like": "oxidase",
    "cat": "catalase", "过氧化氢酶": "catalase", "catalase-like": "catalase",
    "sod": "superoxide dismutase", "超氧化物歧化酶": "superoxide dismutase",
}
FILTERS = {"material", "version", "assay", "activity", "substrate", "ph"} | knowledge_query.EXTRA_FILTERS


def _norm(value):
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _fingerprint(path):
    st = path.stat()
    return st.st_size, st.st_mtime_ns, st.st_ctime_ns


def _safe_path(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError("Registered data path is required")
    path = (root / value).resolve()
    if not path.is_relative_to(root) or any(x in _norm(value) for x in ("sealed", "封存", ".env")):
        raise ValueError("Data access is restricted to registered, non-sealed project files")
    if not path.is_file():
        raise ValueError("Registered data file is unavailable")
    return path


def _scope_applies(obs, version, record):
    """A version/record-scoped fact is never broadcast to another assay."""
    if obs.get("version") not in (None, version.get("key"), version.get("version_id")):
        return False
    if obs.get("record") not in (None, record.get("key"), record.get("record_id")):
        return False
    if "applicable_records" in obs:
        applicable = obs["applicable_records"]
        if not isinstance(applicable, list) or not {record.get("key"), record.get("record_id")} & set(applicable):
            return False
    return True


def _assay_id(obs):
    context = obs.get("context") or {}
    return str(context.get("assay_id", context.get("original_assay_id", "")))


def _object_groups(material, version, record, assay_id, *, include_paths=False):
    """Read actual physical feature parents; never broadcast a sample fact.

    Legacy releases retain their original scope filtering. Pointer paths only
    exist in the read projection and sidecar, never as ref keys in feature data.
    """
    groups = {"material_features": {}, "application_information": {}}
    for group in groups:
        for field, values in material.get(group, {}).items():
            selected = []
            for i, o in enumerate(values or []):
                if _scope_applies(o, version, record) and (not _assay_id(o) or _assay_id(o) == assay_id):
                    item = deepcopy(o)
                    if include_paths and ((group == 'material_features' and material.get('material_feature_schema')) or
                                          (group == 'application_information' and material.get('application_schema'))):
                        item['_feature_path'] = f'/{group}/{field}/{i}'
                    selected.append(item)
            groups[group][field] = selected
    version_index = next((i for i, v in enumerate(material.get('variants', []))
                          if v.get('key') == version.get('key')), None)
    if version_index is not None:
        prefix = f'/variants/{version_index}'
        record_index = next(i for i, r in enumerate(version['records']) if r['record_id'] == record['record_id'])
        parents = [(prefix, version), (prefix + f'/records/{record_index}', record)]
    else:
        record_index = next(i for i, r in enumerate(material.get('material_information_records', []))
                            if r['record_id'] == record['record_id'])
        parents = [(f'/material_information_records/{record_index}', record)]
    for prefix, parent in parents:
        for group in ('material_features','application_information'):
            for field, values in parent.get(group, {}).items():
                for i, o in enumerate(values or []):
                    if not _scope_applies(o,version,record):continue
                    item = deepcopy(o) if include_paths else o
                    if include_paths:
                        item['_feature_path'] = prefix + f'/{group}/{field}/{i}'
                    groups[group].setdefault(field, []).append(item)
    return groups


def _split_record(record, default_sources=(), *, record_path='', copy_values=True):
    inherited = record.get("sources", default_sources)
    if record.get('assay_schema')==ASSAY_SCHEMA:
        yield (str(record['record_id']),tuple(sorted(inherited))),project_record(record,record_path,copy_values=copy_values)
        return
    def key(obs):
        return _assay_id(obs), tuple(sorted(obs.get("sources", inherited)))
    ids = {key(o) for group in ("reaction_conditions", "reported_results")
            for observations in record.get(group, {}).values() for o in observations}
    # Unassigned facts stay unassigned, including facts in a multi-assay envelope.
    for scope in sorted(ids or {("", tuple(sorted(inherited)))}):
        yield scope, {group: {field: [o for o in observations if key(o) == scope]
                               for field, observations in record.get(group, {}).items()
                               if any(key(o) == scope for o in observations)}
                         for group in ("reaction_conditions", "reported_results")}


def _material_overview(material):
    groups = {g: {field: [o for o in (observations or [])
                          if o.get('version') is None and o.get('record') is None
                          and 'applicable_records' not in o and not _assay_id(o)]
                  for field, observations in material.get(g, {}).items()}
              for g in ('material_features', 'application_information')}
    return knowledge_query.content_preview({}, groups)


def _contains(observations, expected, *, activity=False):
    term = _norm(expected)
    if activity:
        term = ACTIVITIES.get(term, term)
    else:
        term=SEARCH_ALIASES.get(term,term)
    return any(term in (ACTIVITIES.get(_norm(o.get("value", "")), _norm(o.get("value", "")))
                        if activity else SEARCH_ALIASES.get(_norm(o.get('value','')),_norm(o.get("value", "")))) for o in observations)


def _same_ph(left, right):
    # Compare explicitly reported scalar pH notation, never infer ranges or units.
    try:
        a, b = Decimal(str(left)), Decimal(str(right))
        return a.is_finite() and b.is_finite() and a == b
    except (InvalidOperation, ValueError):
        return _norm(left) == _norm(right)


class StructuredKnowledgeStore:
    """Streaming queries and bounded metadata/trace caches over registered JSONL.

    ``search(query, dataset=..., material=..., activity=..., substrate=..., ph=...)``
    returns selection IDs. ``read(selection_id)`` is local-only by default;
    ``agent_projection`` requires an explicit trusted sharing grant. Source
    changes invalidate prior selections rather than silently reusing old facts.
    """

    def __init__(self, project_root, entry_path=DEFAULT_ENTRY, *, max_selections=512, max_trace_entries=1024):
        self.root = Path(project_root).resolve()
        self.entry_path = _safe_path(self.root, str(entry_path))
        self.max_selections = max(1, min(int(max_selections), 2048))
        self.max_trace_entries = max(1, min(int(max_trace_entries), 4096))
        self._hashes = {}
        self._selections = OrderedDict()
        self._traces = OrderedDict()
        self._mapping_cache = {}
        self._catalog_cache = {}
        self._entity_cache = {}
        self._adoption_cache = {}
        self._lock = threading.RLock()

    def _hash(self, path, *, verify=False):
        """File stats are a catalog optimization, never a source-read guarantee.

        A rapid same-size Windows rewrite, or a restored modification timestamp,
        can leave the cached stat fingerprint unchanged. Search/read boundaries
        therefore always request an actual content digest.
        """
        stamp = _fingerprint(path)
        previous = self._hashes.get(path)
        if verify or previous is None or previous[0] != stamp:
            previous = (stamp, _digest(path))
            self._hashes[path] = previous
        return previous[1]

    def _datasets(self):
        entry = json.loads(self.entry_path.read_text("utf-8-sig"))
        if entry.get('path_base') == 'directory containing this registry':
            entry = {**entry, 'registry_schema': 'highzyme.knowledge.registry.v1'}
        if entry.get('registry_schema') == 'highzyme.knowledge.registry.v1':
            releases = entry.get('releases', [])
            selected = [r for r in releases if r.get('release_id') == entry.get('active_release')]
            if len(selected) != 1:
                raise ValueError('Knowledge registry must select exactly one active release')
            release = selected[0]
            if release.get('layout') != 'integrated' or release.get('schema') != SCHEMA:
                raise ValueError('Unsupported integrated knowledge release')
            if release.get('material_feature_schema') not in (None, MATERIAL_FEATURE_SCHEMA):
                raise ValueError('Unsupported material-feature release')
            if release.get('assay_schema') not in (None,ASSAY_SCHEMA) or release.get('application_schema') not in (None,APPLICATION_SCHEMA):
                raise ValueError('Unsupported assay or application release')
            name = release.get('title', '整合知识库')
            if not isinstance(name, str) or not name:
                raise ValueError('Knowledge release title is required')
            asset_keys = ('data', 'trace', 'mapping')
            if release.get('entity_schema') not in (None, ENTITY_SCHEMA):
                raise ValueError('Unsupported entity-management release')
            if release.get('entity_schema') == ENTITY_SCHEMA:
                asset_keys += ('entity_management', 'source_catalog')
            paths = {key: _safe_path(self.root, release.get(key)) for key in asset_keys}
            expected = release.get('expected_sha256', {})
            if set(expected) != set(asset_keys) or any(not re.fullmatch(r'[0-9a-f]{64}', str(v)) for v in expected.values()):
                raise ValueError('A published release requires data, trace and mapping hashes')
            return {name: {**paths, 'release_id': release['release_id'],
                'version': release.get('version', release['release_id']), 'expected': expected,
                'field_labels': release.get('field_labels', {}), 'integrated': True,
                'material_feature_schema': release.get('material_feature_schema'),
                'assay_schema':release.get('assay_schema'),'application_schema':release.get('application_schema'),
                'entity_schema':release.get('entity_schema'),
                'adoption_policy':deepcopy(release.get('adoption_policy'))}}
        if entry.get("datasets_separate") is not True or not isinstance(entry.get("datasets"), dict):
            raise ValueError("Separate-dataset material entry contract is required")
        result = {}
        for name, obj in entry["datasets"].items():
            if obj.get("schema") != SCHEMA:
                raise ValueError("Unsupported structured material schema")
            result[name] = {"data": _safe_path(self.root, obj["data"]),
                            "trace": _safe_path(self.root, obj["trace"])}
        return result

    def _verify_release(self, paths):
        """Read-only releases are checked at query/read boundaries, not silently repaired."""
        hashes = {key: self._hash(paths[key], verify=True) for key in ('data', 'trace', 'mapping', 'entity_management', 'source_catalog') if key in paths}
        if paths.get('integrated') and any(hashes[key] != paths['expected'][key] for key in hashes):
            raise ValueError('Published knowledge files changed; publish and activate a verified new release before querying')
        config=paths.get('adoption_policy')
        if config is not None:
            # Revalidate the decision file at each search/read boundary. A valid
            # data file cannot silently inherit stale or edited adoption rules.
            policy=load_adoption_policy(self.root,config,hashes['data'])
            self._adoption_cache={config['sha256']:policy}
        return hashes

    def _entity_assets(self, paths, hashes):
        if paths.get('entity_schema') != ENTITY_SCHEMA:
            return {}, {}
        key = (hashes['entity_management'], hashes['source_catalog'])
        if key not in self._entity_cache:
            management, sources = {}, {}
            for asset, target, id_field in (('entity_management', management, 'material_id'),
                                            ('source_catalog', sources, 'source')):
                with paths[asset].open(encoding='utf-8-sig') as stream:
                    for line in stream:
                        row = json.loads(line)
                        if row[id_field] in target:
                            raise ValueError('Duplicate entity/source management identity')
                        target[row[id_field]] = row
                if self._hash(paths[asset], verify=True) != hashes[asset]:
                    raise ValueError('Entity/source management changed during read')
            self._entity_cache = {key: (management, sources)}
        return self._entity_cache[key]

    def _material_view(self, material, paths, hashes):
        if paths.get('entity_schema') == ENTITY_SCHEMA:
            if material.get('entity_schema') != ENTITY_SCHEMA:
                raise ValueError('Material entity contract does not match release')
            management, _ = self._entity_assets(paths, hashes)
            if material['material_id'] not in management:
                raise ValueError('Missing material entity management')
            return project_entities(material, management[material['material_id']])
        if material.get('entity_schema'):
            raise ValueError('Unregistered material entity contract')
        return material

    def _origins(self, paths, hashes):
        if 'mapping' not in paths:
            return {}
        digest = hashes['mapping']
        if digest in self._mapping_cache:
            return self._mapping_cache[digest]
        index = {}
        with paths['mapping'].open(encoding='utf-8-sig') as stream:
            for line in stream:
                row = json.loads(line)
                item = index.setdefault(row['material_id'], {'datasets': set(), 'records': {}, 'refs': {}, 'sources': {}})
                dataset = row['dataset']; item['datasets'].add(dataset)
                maps = row.get('mappings', {})
                for value in maps.get('sources', {}).values():
                    item['sources'].setdefault(value, set()).add(dataset)
                for value in list(maps.get('record_ids', {}).values()) + list(maps.get('record_keys', {}).values()):
                    item['records'].setdefault(value, set()).add(dataset)
                for value in maps.get('refs', {}).values():
                    item['refs'].setdefault(value, set()).add(dataset)
        if self._hash(paths['mapping'], verify=True) != digest:
            raise ValueError('Origin mapping changed during read; repeat the query')
        self._mapping_cache = {digest: index}
        return index

    def _describe_release(self, name, paths, hashes):
        key = (name, paths.get('release_id'), hashes['data'], hashes.get('mapping'))
        if key in self._catalog_cache:
            return deepcopy(self._catalog_cache[key])
        origins = self._origins(paths, hashes)
        fields, materials, versions, records, source_counts, seen_materials = set(), 0, 0, 0, {}, set()
        classes, applications, activities, record_types, kinetic_records = set(), {}, set(), {}, 0
        with paths['data'].open(encoding='utf-8-sig') as stream:
            for line in stream:
                material = json.loads(line)
                if material.get('schema') != SCHEMA or not material.get('material_id') or material['material_id'] in seen_materials:
                    raise ValueError('Knowledge release requires supported schema and unique material IDs')
                if material.get('material_feature_schema') not in (None, MATERIAL_FEATURE_SCHEMA):
                    raise ValueError('Unsupported material-feature schema')
                if material.get('assay_schema') not in (None,ASSAY_SCHEMA) or material.get('application_schema') not in (None,APPLICATION_SCHEMA):
                    raise ValueError('Unsupported assay or application schema')
                seen_materials.add(material['material_id']); materials += 1
                variants = material.get('variants', []); versions += len(variants)
                all_records = list(material.get('material_information_records', [])) + [r for v in variants for r in v.get('records', [])]
                records += len(all_records)
                for record in all_records:
                    kind = record.get('record_type', 'unspecified')
                    record_types[kind] = record_types.get(kind, 0) + 1
                    view = project_record(record, copy_values=False) if record.get('assay_schema') == ASSAY_SCHEMA else record
                    if kind == 'measurement' and any(knowledge_query.result_present(view, k) for k in ('km', 'vmax')):
                        kinetic_records += 1
                for obj in [material, *variants, *all_records]:
                    knowledge_query.add_facets(obj, classes, applications, activities)
                    view=project_record(obj, copy_values=False) if obj.get('record_id') and obj.get('assay_schema')==ASSAY_SCHEMA else obj
                    for group in GROUPS:
                        fields.update(group + '.' + field for field, values in view.get(group, {}).items() if values)
                    if view is not obj:
                        for group in ('material_features','application_information'):
                            fields.update(group+'.'+field for field,values in obj.get(group,{}).items() if values)
                for origin in origins.get(material['material_id'], {}).get('datasets', []):
                    source_counts[origin] = source_counts.get(origin, 0) + 1
        if self._hash(paths['data'], verify=True) != hashes['data']:
            raise ValueError('Knowledge data changed during catalog read')
        result = {'dataset': name, 'release_id': paths.get('release_id'), 'version': paths.get('version'),
            'material_feature_schema': paths.get('material_feature_schema'),
            'entity_schema': paths.get('entity_schema'),
            'assay_schema':paths.get('assay_schema'),'application_schema':paths.get('application_schema'),
            'materials': materials, 'versions': versions, 'records': records,
            'record_type_counts': record_types, 'measurement_records': record_types.get('measurement', 0),
            'kinetic_records': kinetic_records,
            'facets': {'material_classes': sorted(classes), 'activities': sorted(activities),
                       'applications': [{'major_category': major, 'subcategories': sorted(sub)}
                                        for major, sub in sorted(applications.items())]},
            'data_sha256': hashes['data'], 'trace_sha256': hashes['trace'],
            'mapping_sha256': hashes.get('mapping'), 'origin_material_counts': source_counts,
            'available_fields': sorted(fields), 'field_labels': paths.get('field_labels', {})}
        self._catalog_cache = {key: deepcopy(result)}
        return result

    def catalog(self):
        with self._lock:
            datasets = self._datasets()
            integrated = any(paths.get('integrated') for paths in datasets.values())
            return {"status": "METADATA_ONLY", "read": False, "datasets_separate": not integrated,
                    'layout': 'integrated' if integrated else 'historical_parallel',
                    'source_dataset_filters': ['文献抽取', '外部整合'] if integrated else [],
                    "schema": SCHEMA, "datasets": [self._describe_release(name, paths, self._verify_release(paths))
                        for name, paths in datasets.items()],
                    "filters": sorted(FILTERS),
                    "raw_values_normalized": any(p.get('material_feature_schema') for p in datasets.values()),
                    "material_feature_text_normalized": any(p.get('material_feature_schema') for p in datasets.values()),
                    "numeric_values_normalized": False}

    def search(self, query="", *, dataset=None, source_dataset=None, limit=8, offset=0, **filters):
        return self._search(query, dataset=dataset, source_dataset=source_dataset, limit=limit, offset=offset, **filters)

    def browse(self, query="", *, limit=10, offset=0, material_id=None, record_offset=0,
               page_by='materials', **filters):
        """UI-only material pages and bounded record pages; no saved reads."""
        if material_id is not None and (not isinstance(material_id, str) or len(material_id) > 200):
            raise ValueError('Invalid material selection')
        if type(record_offset) is not int or not 0 <= record_offset <= 100000:
            raise ValueError('Invalid record page')
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError('Browse page limit must be between 1 and 30')
        if page_by not in ('materials', 'records'):
            raise ValueError('Unknown browse pagination mode')
        if page_by == 'records' and (material_id is not None or record_offset):
            raise ValueError('Record pages use the global offset only')
        if page_by == 'materials':
            limit = min(limit, max(1, self.max_selections // 30))
        return self._search(query, limit=limit, offset=offset, _browse=True,
                            _material_id=material_id, _record_offset=record_offset,
                            _page_by=page_by, **filters)

    def _search(self, query="", *, dataset=None, source_dataset=None, limit=8, offset=0,
                _browse=False, _material_id=None, _record_offset=0, _page_by='materials', **filters):
        if not isinstance(query, str) or len(query) > 500 or set(filters) - FILTERS:
            raise ValueError("Unsupported structured knowledge query")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 30:
            raise ValueError("Search limit must be between 1 and 30")
        if type(offset) is not int or not 0 <= offset <= 100000:
            raise ValueError('Search offset must be an integer from 0 to 100000')
        if source_dataset not in (None, '文献抽取', '外部整合'):
            raise ValueError('Unknown source dataset')
        if any(not isinstance(v, (str, int, float)) or isinstance(v, bool) or len(str(v)) > 200
               for k, v in filters.items() if k != 'required_fields'):
            raise ValueError("Filters must be bounded text or raw numeric values")
        knowledge_query.validate(filters)
        terms = [(_norm(t),SEARCH_ALIASES.get(_norm(t),_norm(t))) for t in re.findall(r"[\w.+−-]+", query)]
        with self._lock:
            datasets = self._datasets()
            if dataset is not None:
                if dataset not in datasets:
                    raise ValueError("Unknown registered dataset")
                datasets = {dataset: datasets[dataset]}
            hits, count, material_ids = [], 0, set()
            browse_groups = OrderedDict()
            for row in self._matching_rows(datasets, terms, source_dataset, filters, _material_id):
                metadata = dict(row["metadata"])
                selection_id = metadata["selection_id"]
                count += 1
                material_ids.add(metadata['material_id'])
                keep = count > offset and len(hits) < limit
                if _browse:
                    key = metadata['dataset'] + ':' + metadata['material_id']
                    if key not in browse_groups:
                        browse_groups[key] = {'material_id': metadata['material_id'],
                            'material_name': metadata.get('material_name'), 'dataset': metadata['dataset'],
                            'count': 0, 'measurement_count': 0, '_measurement': [], '_other': [],
                            'overview': row['overview']}
                    group = browse_groups[key]
                    group['count'] += 1
                    measurement = metadata.get('record_type') == 'measurement'
                    group['measurement_count'] += int(measurement)
                    bucket = group['_measurement' if measurement else '_other']
                    if _page_by == 'records':
                        # Earlier materials are complete at this point. Retain a
                        # bounded prefix for measurement-first slicing once this
                        # material's final measurement count is known.
                        preceding = count - group['count']
                        keep = (preceding < offset + limit and
                            len(bucket) < max(0, offset - preceding) + limit)
                    else:
                        selected_group = offset <= len(browse_groups) - 1 < offset + limit
                        keep = selected_group and len(bucket) < _record_offset + 30
                    if keep:
                        metadata['content_preview'] = row['content_preview']
                        metadata['version_label'] = row['version_label']
                        metadata['_browse_location'] = row['location']
                        bucket.append(metadata)
                if keep and not _browse:
                    hits.append(metadata)
                    self._selections[selection_id] = {"metadata": metadata, **row["location"]}
                    self._selections.move_to_end(selection_id)
                    while len(self._selections) > self.max_selections:
                        self._selections.popitem(last=False)
            integrated = any(p.get('integrated') for p in datasets.values())
            if _browse:
                groups = []
                preceding = 0
                candidates = (list(browse_groups.values()) if _page_by == 'records'
                              else list(browse_groups.values())[offset:offset + limit])
                for group in candidates:
                    measurements, other = group.pop('_measurement'), group.pop('_other')
                    if _page_by == 'records':
                        group_start = preceding
                        preceding += group['count']
                        if preceding <= offset or group_start >= offset + limit:
                            continue
                        start = max(0, offset - group_start)
                        size = min(limit - sum(len(g['hits']) for g in groups), group['count'] - start)
                        group['page_by'] = 'records'
                    else:
                        start, size = _record_offset, 30
                    # Measurement-first ordering without dropping source/record identities.
                    selected = (measurements[start:start + size] if start < group['measurement_count'] else [])
                    if len(selected) < size:
                        other_start = max(0, start - group['measurement_count'])
                        selected += other[other_start:other_start + size - len(selected)]
                    group['hits'] = selected
                    for metadata in selected:
                        location = metadata.pop('_browse_location')
                        self._selections[metadata['selection_id']] = {'metadata': deepcopy(metadata), **location}
                        self._selections.move_to_end(metadata['selection_id'])
                    while len(self._selections) > self.max_selections:
                        self._selections.popitem(last=False)
                    group['record_page'] = {'offset': start, 'limit': size,
                        'next_offset': (start + len(selected) if _page_by == 'materials'
                            and start + len(selected) < group['count'] else None)}
                    groups.append(group)
                displayed = (sum(len(g['hits']) for g in groups) if _page_by == 'records' else len(groups))
                total = count if _page_by == 'records' else len(browse_groups)
                return {'status': 'LOCAL_BROWSE', 'read': False, 'groups': groups,
                    'matching_materials': len(browse_groups), 'matching_assay_scopes': count,
                    'page': {'offset': offset, 'limit': limit, 'by': _page_by,
                             'total': total, 'displayed': displayed,
                             'next_offset': offset + displayed if offset + displayed < total else None},
                    'filters': deepcopy(filters), 'query': query}
            return {"status": "METADATA_ONLY", "read": False, "datasets_separate": not integrated,
                    "hits": hits, "matching_assay_scopes": count, "truncated": count > len(hits),
                    'matching_materials': len(material_ids), 'source_dataset': source_dataset,
                    'page': {'offset': offset, 'limit': limit, 'next_offset': offset + len(hits) if offset + len(hits) < count else None},
                    "filters": deepcopy(filters), "query": query}

    def _matching_rows(self, datasets, terms, source_dataset, filters, material_id):
        for name, paths in datasets.items():
            hashes = self._verify_release(paths)
            data_hash = hashes['data']; origins = self._origins(paths, hashes)
            stamp = _fingerprint(paths["data"])
            with paths["data"].open("rb") as stream:
                line_number = 0
                while line := stream.readline():
                    line_number += 1
                    byte_offset = stream.tell() - len(line)
                    material = json.loads(line)
                    if material_id is not None and material['material_id'] != material_id:
                        continue
                    material = self._material_view(material, paths, hashes)
                    overview = _material_overview(material)
                    names = [material.get("material_name", ""), *material.get("aliases", [])]
                    historical_names = material.get('_historical_search_names', [])
                    versions = material.get("variants", []) + [
                        {"key": "material_information", "version_id": None,
                         "records": material.get("material_information_records", [])}]
                    for version in versions:
                        scoped_names = names + historical_names + version.get('original_names', [])
                        if 'material' in filters and not any(_norm(filters['material']) in _norm(n) for n in scoped_names):
                            continue
                        if 'material' not in filters:
                            name_match_status='no material-name filter'
                        elif any(_norm(filters['material'])==_norm(n) for n in names):
                            name_match_status='current display name or confirmed alias'
                        elif any(_norm(filters['material']) in _norm(n) for n in names):
                            name_match_status='partial current-name match; discovery only'
                        else:
                            name_match_status='historical/source sample label; equivalence not asserted'
                        if "version" in filters and str(filters["version"]) not in (version.get("key"), version.get("version_id")):
                            continue
                        for record in version.get("records", []):
                            if not knowledge_query.record_type_matches(record, filters.get("record_kind", "all")):
                                continue
                            for (assay_id, source_scope), scoped in _split_record(record, material.get("default_sources", []), copy_values=False):
                                origin = origins.get(material['material_id'], {})
                                record_origins = sorted(origin.get('records', {}).get(record['record_id'],
                                    origin.get('records', {}).get(record.get('key'), set())))
                                scope_origins = set().union(*(origin.get('sources', {}).get(sid, set()) for sid in source_scope))
                                if scope_origins:
                                    record_origins = sorted(scope_origins)
                                if not paths.get('integrated'):
                                    record_origins = [name]
                                if source_dataset is not None and source_dataset not in record_origins:
                                    continue
                                if "assay" in filters and str(filters["assay"]) != assay_id:
                                    continue
                                conditions = scoped["reaction_conditions"]
                                if any(not _contains(conditions.get(field, []), filters[f], activity=(f == "activity"))
                                       for f, field in (("activity", "enzyme_mimic_type"), ("substrate", "substrate")) if f in filters):
                                    continue
                                if "ph" in filters and not any(_same_ph(o.get("value"), filters["ph"])
                                                               for o in conditions.get("ph", [])):
                                    continue
                                if record.get('assay_schema')==ASSAY_SCHEMA and 'ph' in filters and 'substrate' in filters:
                                    # A substrate from a prestep must not match the
                                    # pH of a different stage in the same assay.
                                    if not any(stage.get('ph') and _same_ph(stage['ph']['value'],filters['ph']) and
                                        _contains([{'value':c.get('substance')} for c in stage.get('components',[]) if c.get('role')=='substrate'],filters['substrate'])
                                        for stage in record['reaction_conditions'].get('stages',[])):
                                        continue
                                object_fields = _object_groups(material, version, record, assay_id)
                                scope_dois = [s['doi'] for sid, s in material.get('sources', {}).items()
                                              if isinstance(s, dict) and s.get('doi') and sid in source_scope]
                                if not knowledge_query.matches(record, scoped, object_fields, filters, scope_dois):
                                    continue
                                text = _norm(json.dumps({"names": scoped_names, "scoped": scoped, **object_fields}, ensure_ascii=False)) if terms else ""
                                if terms and not all(any(t in text for t in alternatives) for alternatives in terms):
                                    continue
                                identity = [name, material["material_id"], version.get("version_id"),
                                            record["record_id"], assay_id, source_scope, data_hash,
                                            paths.get('release_id'), hashes.get('mapping')]
                                selection_id = "K:" + hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:32]
                                metadata = {"selection_id": selection_id, "dataset": name,
                                    "material_id": material["material_id"], "material_name": material.get("material_name"),
                                    "version_id": version.get("version_id"), "record_id": record["record_id"],
                                    "assay_id": assay_id or None, "assay_source_ids": list(source_scope),
                                    "record_type": record.get("record_type"),
                                    "preview": knowledge_query.preview(scoped, object_fields),
                                    "association": record.get("association"), "data_sha256": data_hash,
                                    'release_id': paths.get('release_id'), 'data_version': paths.get('version'),
                                    'mapping_sha256': hashes.get('mapping'),
                                    'origin_datasets': record_origins,
                                    'material_origin_datasets': sorted(origin.get('datasets', set(record_origins))),
                                    "available_fields": {g: sorted(f for f, obs in rows.items() if obs)
                                                         for g, rows in {**object_fields, **scoped}.items()},
                                    "source_dois": sorted({str(s['doi']) for sid, s in material.get('sources', {}).items()
                                        if isinstance(s, dict) and s.get('doi') and sid in source_scope}),
                                    "read": False, "access_level": "METADATA_ONLY"}
                                if paths.get('entity_schema'):
                                    metadata.update({'entity_schema':ENTITY_SCHEMA,
                                        'scope_status':record.get('_scope_status'),
                                        'version_scope_status':version.get('_scope_status'),
                                        'identity_review':[deepcopy(x) for x in material.get('_identity_review',[]) if x['target_id'] in (material['material_id'],version.get('version_id'))],
                                        'name_match_status':name_match_status,
                                        'source_dois_role':'historically associated references; not a source-read assertion'})
                                yield {"metadata": metadata, "location": {"offset": byte_offset, "line": line_number, "version_key": version.get("key"), "record_key": record.get("key")},
                                    "overview": overview, "content_preview": knowledge_query.content_preview(scoped, object_fields),
                                    "version_label": version.get("label") or version.get("name") or version.get("key")}
            if (_fingerprint(paths["data"]) != stamp
                    or self._hash(paths["data"], verify=True) != data_hash):
                raise ValueError("Structured data changed during search; repeat the query")
            if paths.get('entity_schema') and self._verify_release(paths)!=hashes:
                raise ValueError('Entity/source management changed during search')

    def _read_traces(self, dataset, path, material_id, refs):
        trace_hash = self._hash(path, verify=True)
        found, missing, pending_cache = {}, [], []
        for ref in refs:
            key = (dataset, trace_hash, material_id, ref)
            if key in self._traces:
                found[ref] = deepcopy(self._traces[key])
                self._traces.move_to_end(key)
            else:
                missing.append(ref)
        if missing:
            pending = set(missing)
            stamp = _fingerprint(path)
            with path.open("r", encoding="utf-8-sig") as stream:
                for line_number, line in enumerate(stream, 1):
                    row = json.loads(line)
                    pointer_key = '@feature:' + row['observation_path'] if row.get('observation_path') else None
                    if row.get('material_id') == material_id and pointer_key in missing:
                        trace = found.setdefault(pointer_key, {'material_id': material_id,
                            'observation_path': row['observation_path'], 'lineage': []})
                        item = {k: deepcopy(row[k]) for k in ('original_ref', 'original_field', 'original_path',
                            'original_trace', 'source', 'target_type', 'target_id', 'field_path', 'evidence', 'evidence_status') if k in row}
                        if row.get('target_id'):
                            # A normalized stable-target link supersedes the matching
                            # inherited projection, while old file bytes remain intact.
                            trace['lineage'] = [x for x in trace['lineage'] if
                                (x.get('original_ref'), x.get('original_path')) != (row.get('original_ref'), row.get('original_path'))]
                            trace['target'] = {k:row[k] for k in ('target_type','target_id','field_path')}
                        trace['lineage'].append(item)
                        pending.discard(pointer_key)
                    elif row.get("material_id") == material_id and row.get("ref") in pending:
                        # Historical numeric normalization is deliberately excluded.
                        trace = {k: deepcopy(row[k]) for k in ("material_id", "ref", "original", "detail_ref",
                            "source_locator", "original_quote", "scientific_review", "archived_context", "origin") if k in row}
                        trace["trace_file_line"] = line_number
                        found[row["ref"]] = trace
                        key = (dataset, trace_hash, material_id, row["ref"])
                        if len(json.dumps(trace, ensure_ascii=False)) <= 24000:
                            pending_cache.append((key, trace))
                        pending.remove(row["ref"])
                        if not pending and not any(r.startswith('@feature:') for r in missing):
                            break
            if _fingerprint(path) != stamp:
                raise ValueError("Trace data changed during read; repeat the query")
        if self._hash(path, verify=True) != trace_hash:
            raise ValueError("Trace data changed during read; repeat the query")
        # Do not bind unverified, mid-rewrite content to the old source digest.
        # Cache entries are committed only after the complete source recheck.
        for key, trace in pending_cache:
            self._traces[key] = trace
            while len(self._traces) > self.max_trace_entries:
                self._traces.popitem(last=False)
        for ref, trace in found.items():
            if ref.startswith('@feature:') and len(json.dumps(trace, ensure_ascii=False)) <= 24000:
                self._traces[(dataset, trace_hash, material_id, ref)] = deepcopy(trace)
                while len(self._traces) > self.max_trace_entries:
                    self._traces.popitem(last=False)
        return found, trace_hash

    def read(self, selection_id, *, fields=None, share_with_agent=False, complete=False):
        if not isinstance(share_with_agent, bool):
            raise ValueError("Sharing permission must be a trusted boolean")
        if fields is not None and (not isinstance(fields, list) or len(fields) > 40
                                  or any(not isinstance(f, str) or len(f) > 100 for f in fields)):
            raise ValueError("Fields must be a bounded list of group.field names")
        with self._lock:
            if selection_id not in self._selections:
                raise ValueError("Unknown or expired selection; search again before reading")
            selected = self._selections[selection_id]
            metadata = selected["metadata"]
            paths = self._datasets().get(metadata['dataset'])
            if paths is None or paths.get('release_id') != metadata.get('release_id'):
                raise ValueError('Knowledge release changed; search again before reading')
            hashes = self._verify_release(paths)
            if metadata.get('mapping_sha256') != hashes.get('mapping'):
                raise ValueError('Knowledge origin mapping changed; search again before reading')
            if self._hash(paths["data"], verify=True) != metadata["data_sha256"]:
                raise ValueError("Source data changed; selection is stale and must be searched again")
            with paths["data"].open("rb") as stream:
                stream.seek(selected["offset"])
                material = self._material_view(json.loads(stream.readline()), paths, hashes)
            if material.get("material_id") != metadata["material_id"]:
                raise ValueError("Selection identity mismatch")
            versions = material.get("variants", []) + [{"key": "material_information", "version_id": None,
                "records": material.get("material_information_records", [])}]
            version = next(v for v in versions if v.get("key") == selected["version_key"])
            record = next(r for r in version["records"] if r["record_id"] == metadata["record_id"])
            assay_id = metadata["assay_id"] or ""
            prefix=record_pointer(material,version,record) if record.get('assay_schema')==ASSAY_SCHEMA else ''
            scoped = dict(_split_record(record, material.get("default_sources", []),record_path=prefix))[
                (assay_id, tuple(metadata["assay_source_ids"]))]
            groups = {**_object_groups(material, version, record, assay_id, include_paths=True), **scoped}
            observations, unknown_fields = [], []
            available = {g + "." + f for g, rows in groups.items() for f, obs in rows.items() if obs}
            if fields is not None:
                fields = [name for field in fields for name in
                          (sorted(name for name in available if name.startswith(field + '.')) if field in groups else [field])]
                unknown_fields = sorted(set(fields) - available)
            for group, rows in groups.items():
                inherited = record.get("sources", material.get("default_sources", [])) if group in (
                    "reaction_conditions", "reported_results") else material.get("default_sources", [])
                for field, values in rows.items():
                    if fields is not None and group + "." + field not in fields:
                        continue
                    for original in values:
                        if fields is None and original.get('_compatibility_alias'):continue
                        obs = deepcopy(original)
                        compatibility=obs.pop('_compatibility_alias',False)
                        if compatibility:obs['projection_kind']='compatibility alias of a stored observation'
                        feature_path = obs.pop('_feature_path', None)
                        if feature_path is not None:
                            obs['observation_path'] = feature_path
                            obs['source_ids'] = []
                            obs['sources_resolved'] = {url: {'url': url, **(
                                {'doi': url.removeprefix('https://doi.org/')} if url.startswith('https://doi.org/') else {})}
                                for url in obs.get('source', [])}
                            if paths.get('entity_schema'):
                                _, source_catalog = self._entity_assets(paths, hashes)
                                for url, resolved in obs['sources_resolved'].items():
                                    if url not in source_catalog:
                                        raise ValueError('Scientific source missing from source catalog')
                                    entry=source_catalog[url]
                                    resolved['source_type']=entry['source_type']
                                    resolved['evidence_role']='actual source declared on this stored observation; not independently re-read'
                                    resolved['historical_associations']=[deepcopy(x) for x in entry.get('legacy_mentions',[]) if x['material_id']==metadata['material_id']]
                        else:
                            obs["source_ids"] = deepcopy(obs.get("sources", inherited))
                            obs["sources_resolved"] = {sid: deepcopy(material.get("sources", {}).get(sid)) for sid in obs["source_ids"]}
                        obs.update({"field": group + "." + field, "material_id": metadata["material_id"],
                                    "version_id": metadata["version_id"], "record_id": metadata["record_id"],
                                    "assay_id": metadata["assay_id"]})
                        observations.append(obs)
            all_count = len(observations)
            if not complete:
                observations = observations[:80]
            refs = {o["ref"] for o in observations if o.get("ref")}
            refs.update('@feature:' + o['observation_path'] for o in observations if o.get('observation_path'))
            traces, trace_hash = self._read_traces(metadata["dataset"], paths["trace"], metadata["material_id"], refs)
            origins = self._origins(paths, hashes)
            for obs in observations:
                obs["trace"] = traces.get('@feature:' + obs['observation_path'] if obs.get('observation_path') else obs.get('ref'))
                obs["trace_status"] = "FOUND" if obs["trace"] else "UNAVAILABLE"
                trace_origin = (obs['trace'] or {}).get('origin', {})
                obs['origin_datasets'] = ([trace_origin['dataset']] if trace_origin.get('dataset') else
                    sorted(origins.get(metadata['material_id'], {}).get('refs', {}).get(obs.get('ref'), set())))
                if obs.get('observation_path') and obs['trace']:
                    obs['origin_datasets'] = sorted({origin for lineage in obs['trace'].get('lineage', [])
                        for origin in origins.get(metadata['material_id'], {}).get('refs', {}).get(lineage.get('original_ref'), set())})
            config=paths.get('adoption_policy')
            if config:
                decisions=self._adoption_cache[config['sha256']].get(metadata['material_id'],[])
                observations=[annotate_adoption(o,decisions,metadata.get('version_id')) for o in observations]
            while not complete and observations and len(json.dumps(observations, ensure_ascii=False)) > 60000:
                observations.pop()
            if self._hash(paths["data"], verify=True) != metadata["data_sha256"]:
                raise ValueError("Structured source changed during read; search again before using facts")
            if paths.get('entity_schema'):
                for asset in ('entity_management','source_catalog'):
                    if self._hash(paths[asset],verify=True)!=hashes[asset]:
                        raise ValueError('Entity/source management changed during read')
            return {"status": "READ" if observations else "NO_SELECTED_FACTS", "access_level": "CURATED_EXTRACTION_UNVERIFIED", "read": bool(observations),
                "citable": False, "source_document_read": False,
                "selection": deepcopy(metadata), "observations": observations, "unknown_fields": unknown_fields,
                "coverage": {"observations_returned": len(observations), "observations_selected": all_count,
                             "truncated": all_count > len(observations), "full_paper_read": False,
                             "record_scope_only": True},
                "provenance": {"data_sha256": metadata["data_sha256"], "trace_sha256": trace_hash,
                    'release_id': metadata.get('release_id'), 'data_version': metadata.get('data_version'),
                    'mapping_sha256': hashes.get('mapping'),
                    **({'entity_management_sha256':hashes['entity_management'],'source_catalog_sha256':hashes['source_catalog']} if paths.get('entity_schema') else {}),
                    "data_file": str(paths["data"].relative_to(self.root)), "data_line": selected["line"],
                    "trace_file": str(paths["trace"].relative_to(self.root))},
                "permission": {"share_with_agent": share_with_agent},
                "boundaries": ["Raw values and units are retained without numerical normalization.",
                    "Source roles, missing provenance and original pairing uncertainty remain visible.",
                    "Different datasets, versions and assay contexts are not merged.",
                    "Structured extraction is not independent scientific validation or a full-paper read."] +
                    (["Final closeout decisions are applied. REPORTED_ONLY observations preserve history and are not adopted for quantitative use."] if paths.get('adoption_policy') else [])}

    @staticmethod
    def agent_projection(result):
        if result.get("permission", {}).get("share_with_agent") is not True or result.get("read") is not True:
            raise ValueError("Explicit sharing permission and an actual read are required")
        return deepcopy({k: result[k] for k in ("status", "access_level", "read", "citable", "source_document_read", "selection", "observations",
            "unknown_fields", "coverage", "provenance", "boundaries")})
