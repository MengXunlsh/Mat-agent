"""Pinned current assets and provenance; historical migration is not a runtime dependency."""
from __future__ import annotations

import hashlib
import json
import ntpath
from functools import lru_cache
from pathlib import Path, PureWindowsPath

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / 'data'
MODEL_ROOT = PROJECT_ROOT / 'models'
CONFIG_PATH = PROJECT_ROOT / 'runtime/current_app.json'
TRACE_ROOT = PROJECT_ROOT / 'runtime/traces/prediction_workflow'
SOURCE = '885d'
PROVENANCE_OWNER = 'main'
PAID_DISABLED_MESSAGE = '当前迁移入口仅支持免费本地模式；收费 API 与外部模型入口已禁用。'


def _safe_relative(value: str) -> tuple[str, ...]:
    p = PureWindowsPath(value)
    if (not p.parts or p.is_absolute() or p.drive or p.root or '..' in p.parts
            or any(':' in x for x in p.parts)):
        raise ValueError('Invalid registered relative path')
    return p.parts


def _key(value: str) -> str:
    return ntpath.normpath(value).casefold()


@lru_cache(maxsize=1)
def asset_index():
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    if config.get('source') != SOURCE or config.get('paid_api_enabled') is not False or config.get('external_models_enabled') is not False:
        raise ValueError('Current application policy must remain source-pinned and local-only')
    if config.get('rag_provenance_owner') != PROVENANCE_OWNER:
        raise ValueError('RAG provenance owner must match the historical main-to-885d restoration')
    plan = PROJECT_ROOT.joinpath(*_safe_relative(config['asset_index']))
    if not plan.resolve().is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError('Asset index is outside current project')
    blob = plan.read_bytes()
    if hashlib.sha256(blob).hexdigest() != config['asset_index_sha256']:
        raise ValueError('Current asset index changed; review application configuration')
    index = {}; roots = {}
    for line in blob.decode('utf-8-sig').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        k = (row['source'], _key(row['relative_path']))
        if k in index and (index[k]['destination'], index[k]['sha256']) != (row['destination'], row['sha256']):
            raise ValueError('Ambiguous source identity in asset index')
        _safe_relative(row['relative_path'])
        _safe_relative(row['destination'])
        if not isinstance(row['bytes'], int) or row['bytes'] < 0 or len(row['sha256']) != 64:
            raise ValueError('Invalid registered asset fingerprint')
        index[k] = row
        prefix = _key(row['root']).rstrip('\\') + '\\'
        if row['source'] in roots and roots[row['source']] != prefix:
            raise ValueError('Ambiguous historical root for source identity')
        roots[row['source']] = prefix
    return index, roots


def registered_asset(old_relative_path: str, *, source: str = SOURCE) -> Path:
    """Resolve a registered file, with no lookup/open against an old root."""
    _safe_relative(old_relative_path)
    index, _ = asset_index()
    row = index.get((source, _key(old_relative_path)))
    if row is None:
        raise ValueError('Required source file absent from current asset index')
    path = PROJECT_ROOT.joinpath(*_safe_relative(row['destination'])).resolve()
    if not path.is_relative_to(PROJECT_ROOT.resolve()) or not path.is_file():
        raise ValueError('Required registered file is unavailable inside current project')
    if path.stat().st_size != row['bytes']:
        raise ValueError('Registered file size changed')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != row['sha256']:
        raise ValueError('Registered asset content changed')
    return path


def model_package(old_package: str) -> Path:
    path = registered_asset('projects/highzyme/' + old_package.strip('/') + '/model.json').parent
    if not path.is_relative_to(MODEL_ROOT.resolve()):
        raise ValueError('Model mapping is outside current model store')
    return path


def budget_baseline() -> Path:
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    path = PROJECT_ROOT.joinpath(*_safe_relative(config['budget_baseline'])).resolve()
    if not path.is_relative_to((PROJECT_ROOT/'runtime').resolve()) or not path.is_file():
        raise ValueError('Runtime budget baseline is unavailable')
    if hashlib.sha256(path.read_bytes()).hexdigest() != config['budget_baseline_sha256']:
        raise ValueError('Historical cumulative budget baseline changed')
    return path


def provenance_path(old_path, expected_sha256=None):
    """Translate display-only source paths without opening legacy locations."""
    if not isinstance(old_path, str) or not old_path:
        return None
    index, roots = asset_index()
    if PureWindowsPath(old_path).is_absolute():
        old_key = _key(old_path)
        for source, prefix in roots.items():
            if old_key.startswith(prefix):
                try:
                    relative = ntpath.relpath(old_path, prefix)
                    row = index.get((source, _key(relative)))
                    if row is None or (expected_sha256 is not None and row['sha256'] != expected_sha256):
                        return None
                    return str(registered_asset(relative, source=source))
                except ValueError:
                    return None
        return None
    candidates = ('projects/highzyme/' + old_path.replace('\\', '/'), old_path)
    for candidate in candidates:
        try:
            row = index.get((SOURCE, _key(candidate)))
            if row is not None and (expected_sha256 is None or row['sha256'] == expected_sha256):
                return str(registered_asset(candidate))
        except ValueError:
            continue
    # The restored RAG index in 885d references original papers held by main.
    # Resolve only the exact relative path AND the source-index pinned hash.
    # This is byte-identical provenance, never a latest-version substitution.
    if isinstance(expected_sha256, str) and len(expected_sha256) == 64:
        matches = [row for source in (PROVENANCE_OWNER,) for candidate in candidates
                   if (row := index.get((source, _key(candidate)))) is not None
                   and row['sha256'] == expected_sha256]
        destinations = {row['destination'] for row in matches}
        if len(destinations) == 1:
            row = matches[0]
            try:
                return str(registered_asset(row['relative_path'], source=row['source']))
            except ValueError:
                return None
    return None
