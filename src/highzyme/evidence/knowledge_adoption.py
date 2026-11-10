"""Apply explicit data-closeout decisions without deleting historical facts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path


def load_adoption_policy(root, config, data_sha256):
    if config is None:
        return {}
    if not isinstance(config, dict) or set(config) != {'schema','path','sha256','data_sha256'}:
        raise ValueError('Invalid knowledge adoption policy registration')
    if config['schema'] != 'highzyme.knowledge.adoption.v1' or config['data_sha256'] != data_sha256:
        raise ValueError('Knowledge adoption policy belongs to another data version')
    root=Path(root).resolve();path=(root/config['path']).resolve()
    if not path.is_relative_to(root) or any(x in str(path).casefold() for x in ('.env','sealed','封存')):
        raise ValueError('Knowledge adoption policy path is outside the allowed scope')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=config['sha256']:
        raise ValueError('Knowledge adoption decisions changed; publish a new release')
    result={}
    for line in raw.decode('utf8').splitlines():
        if not line.strip():continue
        row=json.loads(line)
        if row.get('decision') not in ('ADOPT','ABANDON'):
            raise ValueError('Knowledge closeout must contain terminal decisions only')
        if row['decision']=='ABANDON' and row.get('material_id') and row.get('path'):
            result.setdefault(row['material_id'],[]).append(row)
    return result


def annotate_adoption(observation, decisions, version_id):
    item=deepcopy(observation);path=item.get('observation_path','');matched=[]
    for row in decisions:
        if row['kind']=='sample_identity':
            applies=row.get('target_id')==version_id
        else:
            rp=row['path'];applies=bool(path) and (path==rp or path.startswith(rp+'/'))
        if applies:matched.append(row)
    if not matched:return item
    kinds=sorted({r['kind'] for r in matched})
    item['adoption']={'status':'REPORTED_ONLY','quantitative_use':False,
        'decision_ids':[r['issue_id'] for r in matched], 'unresolved_fields':kinds,
        'decision':'Final decision: do not fill or adopt the unsupported interpretation; preserve the original reported observation.',
        'reason':'Sample identity is not established.' if 'sample_identity' in kinds else
                 'Required unit, reactant pairing, concentration meaning or measurement context is not established.'}
    return item
