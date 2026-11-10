"""Read projections over physically separated, English assay records.

Compatibility aliases are computed at read time; they are not another stored
copy and cannot add a concentration, unit, role or pairing absent in the data.
"""
from copy import deepcopy

ASSAY_SCHEMA='highzyme.assay.structured.v1'
APPLICATION_SCHEMA='highzyme.application.english.v1'
SEARCH_ALIASES={
    'tmb':'3,3′,5,5′-tetramethylbenzidine',
    'abts':'2,2′-azino-bis(3-ethylbenzothiazoline-6-sulfonic acid)',
    'opd':'o-phenylenediamine','h2o2':'hydrogen peroxide','h₂o₂':'hydrogen peroxide',
    'o2':'molecular oxygen','pod':'peroxidase','oxd':'oxidase','cat':'catalase',
    'sod':'superoxide dismutase'}


def project_record(record,prefix='', *, copy_values=True):
    groups={'reaction_conditions':{},'reported_results':{}}
    def emit(group,field,observation,path,*,alias=False,value=None,unit=None):
        if not isinstance(observation,dict) or not observation.get('source'):return
        item=deepcopy(observation) if copy_values else dict(observation)
        if value is not None:item['value']=deepcopy(value) if copy_values else value
        elif 'value' not in item:item['value']={k:(deepcopy(v) if copy_values else v) for k,v in observation.items() if k!='source'}
        if unit is not None:item['unit']=unit
        item['_feature_path']=prefix+path
        if alias:item['_compatibility_alias']=True
        groups[group].setdefault(field,[]).append(item)
    conditions=record.get('reaction_conditions',{})
    for field in ('activity_type','assay_method'):
        obs=conditions.get(field)
        if obs:
            emit('reaction_conditions',field,obs,'/reaction_conditions/'+field)
            if field=='activity_type':emit('reaction_conditions','enzyme_mimic_type',obs,'/reaction_conditions/'+field,alias=True)
    for si,stage in enumerate(conditions.get('stages',[])):
        sp=f'/reaction_conditions/stages/{si}'
        for field in ('ph','temperature','duration','total_volume','ionic_strength','illumination'):
            obs=stage.get(field)
            if obs:
                emit('reaction_conditions','stages.'+field,obs,sp+'/'+field)
                if field in ('ph','temperature','duration','ionic_strength'):
                    emit('reaction_conditions',{'duration':'reaction_time'}.get(field,field),obs,sp+'/'+field,alias=True)
        for ci,component in enumerate(stage.get('components',[])):
            cp=sp+f'/components/{ci}'
            emit('reaction_conditions','stages.components',component,cp,value={k:v for k,v in component.items() if k!='source'})
            role=component.get('role');substance=component.get('substance')
            if role in ('substrate','co-substrate') and substance:
                field='substrate' if role=='substrate' else 'co_substrate'
                emit('reaction_conditions',field,component,cp,alias=True,value=substance)
                if component.get('concentration'):
                    q=component['concentration'];emit('reaction_conditions',field+'_concentration',component,cp,alias=True,value=q['value'],unit=q.get('unit'))
            if role=='catalyst':
                for key,target in [('concentration','nanozyme_concentration'),('amount','nanozyme_dose')]:
                    q=component.get(key)
                    if q:emit('reaction_conditions',target,component,cp,alias=True,value=q['value'],unit=q.get('unit'))
            if role=='buffer' and substance:
                emit('reaction_conditions','buffer',component,cp,alias=True,value=substance)
                q=component.get('concentration')
                if q:emit('reaction_conditions','buffer_concentration',component,cp,alias=True,value=q['value'],unit=q.get('unit'))
    for i,obs in enumerate(conditions.get('readout',[])):
        emit('reaction_conditions','readout',obs,f'/reaction_conditions/readout/{i}',value={k:v for k,v in obs.items() if k!='source'})
    for field,observations in record.get('reported_results',{}).items():
        for i,obs in enumerate(observations):
            emit('reported_results',field,obs,f'/reported_results/{field}/{i}')
            if field=='additional_results':
                emit('reported_results','other_metrics',obs,f'/reported_results/{field}/{i}',alias=True)
    return groups


def record_pointer(material,version,record):
    for vi,v in enumerate(material.get('variants',[])):
        if v.get('key')==version.get('key'):
            ri=next(i for i,r in enumerate(v['records']) if r['record_id']==record['record_id'])
            return f'/variants/{vi}/records/{ri}'
    ri=next(i for i,r in enumerate(material.get('material_information_records',[])) if r['record_id']==record['record_id'])
    return f'/material_information_records/{ri}'
