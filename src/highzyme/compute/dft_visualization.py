"""Registered grid exports and integrity-checked, case-owned visualization data."""
from pathlib import Path
import hashlib,json,re

MAX_ARTIFACT_BYTES=16*1024*1024
GRID_NAME=re.compile(r'(?:D[abts]|Psi_[ab]_\d+_[A-Za-z0-9_-]+)\.cube\Z')
BASE_ARTIFACTS={'request.json','input.xyz','final.xyz','psi4.out','stdout.log','result.json',
    'qe.in','qe.out','input.cif','final.cif','visualization.json','wavefunction.molden'}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def cube_summary(path):
    import numpy as np
    lines=Path(path).read_text('utf8').splitlines()
    nat=int(lines[2].split()[0]);axes=[line.split() for line in lines[3:6]]
    shape=[abs(int(a[0])) for a in axes];vectors=np.array([[float(x) for x in a[1:4]] for a in axes])
    start=6+abs(nat)+(1 if nat<0 else 0)
    values=np.fromstring(' '.join(lines[start:]).replace('D','E'),sep=' ')
    if len(values)!=int(np.prod(shape)) or not np.all(np.isfinite(values)):
        raise ValueError('Cube grid shape or values are invalid')
    return {'shape':shape,'grid_points':len(values),'minimum':float(values.min()),'maximum':float(values.max()),
            'integral':float(values.sum()*abs(np.linalg.det(vectors))),'coordinate_unit':'bohr' if int(axes[0][0])>0 else 'angstrom'}

def export_psi4(psi4,wfn,folder,settings):
    """Called inside the isolated worker while its actual wavefunction is alive."""
    from dft_schema import validate_visualization
    positions=(wfn.molecule().geometry().to_array()*psi4.constants.bohr2angstroms).tolist()
    validate_visualization(settings,positions)
    folder=Path(folder);props=settings['properties'];na,nb=wfn.nalpha(),wfn.nbeta();nbf=wfn.basisset().nbf()
    selected=[]
    if 'frontier_orbitals' in props:
        alpha=set([na,na+1,nb])|set(range(nb+1,na+1))
        beta={nb,nb+1}
        selected=[i for i in sorted(alpha) if 1<=i<=nbf]+[-i for i in sorted(beta) if 1<=i<=nbf]
        if len(selected)>12:raise ValueError('Frontier orbital export exceeds its bounded count')
    tasks=(['DENSITY'] if any(p in props for p in ['electron_density','spin_density']) else [])+(['ORBITALS'] if selected else [])
    opts={'cubeprop_tasks':tasks,'cubic_grid_spacing':[settings['grid_spacing_bohr']]*3,
          'cubic_grid_overage':[settings['padding_bohr']]*3,'cubeprop_filepath':str(folder)}
    if selected:opts['cubeprop_orbitals']=selected
    psi4.set_options(opts);psi4.cubeprop(wfn)
    psi4.molden(wfn,str(folder/'wavefunction.molden'))
    grids=[]
    for path in sorted(folder.glob('*.cube')):
        if not GRID_NAME.fullmatch(path.name) or path.stat().st_size>MAX_ARTIFACT_BYTES:
            raise ValueError('Grid artifact exceeds its registered format or size')
        name=path.name;match=re.fullmatch(r'Psi_([ab])_(\d+)_.+\.cube',name)
        if match:
            spin='alpha' if match[1]=='a' else 'beta';index=int(match[2]);count=na if spin=='alpha' else nb
            energy=float((wfn.epsilon_a() if spin=='alpha' else wfn.epsilon_b()).to_array()[index-1])
            role='SOMO' if spin=='alpha' and nb<index<=na else 'HOMO' if index==count else 'LUMO' if index==count+1 else 'occupied'
            label=f'{spin} {index} · {role}'
            info={'kind':'orbital','spin':spin,'orbital_index':index,'occupation':1 if index<=count else 0,
                  'energy_hartree':energy,'role':role,'label':label,'units':'bohr^(-3/2)','default_isovalue':.04}
        else:
            names={'Dt':('electron_density','Total electron density'), 'Ds':('spin_density','Spin density (alpha − beta)'),
                   'Da':('alpha_density','Alpha electron density'),'Db':('beta_density','Beta electron density')}
            kind,label=names[path.stem];info={'kind':kind,'label':label,'units':'electron/bohr^3','default_isovalue':.02 if kind!='spin_density' else .004}
        grids.append({**info,'name':name,'bytes':path.stat().st_size,'sha256':digest(path),'grid':cube_summary(path)})
    requested_density=any(p in props for p in ['electron_density','spin_density'])
    if requested_density and not {'Dt.cube','Ds.cube'}<={g['name'] for g in grids}:raise ValueError('Requested density grids are missing')
    if selected and sum(g['kind']=='orbital' for g in grids)!=len(selected):raise ValueError('Requested orbital grids are missing')
    grids.sort(key=lambda g:({'electron_density':0,'spin_density':1,'orbital':2,'alpha_density':3,'beta_density':4}[g['kind']],g['name']))
    manifest={'schema':1,'status':'COMPLETED','settings':settings,'nalpha':na,'nbeta':nb,'grids':grids,
              'molden':{'name':'wavefunction.molden','sha256':digest(folder/'wavefunction.molden')},
              'interpretation':'Orbital signs represent wavefunction phase. Spin density is alpha minus beta. Neither is adsorption-induced charge-density difference.'}
    tmp=folder/'visualization.tmp'
    tmp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(folder/'visualization.json')
    return {'status':'COMPLETED','manifest_sha256':digest(folder/'visualization.json'),'grids':len(grids)}

def registered_names(folder):
    path=Path(folder)/'visualization.json'
    if not path.is_file():return set()
    data=json.loads(path.read_text('utf8'));rows=data.get('grids',[])
    if len(rows)>16 or any(not GRID_NAME.fullmatch(r.get('name','')) for r in rows):raise ValueError('Invalid registered visualization artifacts')
    return {r['name'] for r in rows}

def visualization_data(store,row):
    public=store.public(row,include_result=True);folder=store.folder(row['job_id']);task=json.loads((folder/'request.json').read_text('utf8'))
    result=public.get('calculation_result');s=result or task['structure']
    data={'job_id':row['job_id'],'status':row['status'],'label':task['label'],
          'structure':{'symbols':s['symbols'],'positions_angstrom':s['positions_angstrom'],
                       'cell_angstrom':s.get('cell_angstrom'),'charge':s.get('charge'),
                       'multiplicity':s.get('multiplicity'),'source':task['structure']['source'],
                       'geometry_kind':'optimized' if result and result.get('optimization_converged') else 'calculated' if result else 'input'},
          'grids':[],'electronic_status':'NOT_REQUESTED'}
    visual=(result or {}).get('visualization',{})
    if visual.get('status')=='COMPLETED':
        path=folder/'visualization.json'
        if digest(path)!=visual.get('manifest_sha256'):raise ValueError('Visualization manifest integrity check failed')
        names=registered_names(folder);manifest=json.loads(path.read_text('utf8'))
        data.update(grids=manifest['grids'],electronic_status='COMPLETED',grid_settings=manifest['settings'],
                    interpretation=manifest['interpretation'],molden=manifest['molden'])
        if len(names)!=len(manifest['grids']):raise ValueError('Duplicate grid artifact names')
    elif visual.get('status')=='FAILED':data.update(electronic_status='FAILED',reason=visual.get('reason'))
    return data

def artifact_bytes(store,row,name):
    data=visualization_data(store,row);folder=store.folder(row['job_id'])
    if name not in BASE_ARTIFACTS and name not in {g['name'] for g in data['grids']}:
        raise ValueError('Artifact is not registered for this calculation')
    path=folder/name
    if path.parent!=folder or not path.is_file() or path.stat().st_size>MAX_ARTIFACT_BYTES:
        raise ValueError('Artifact is unavailable or exceeds the read limit')
    blob=path.read_bytes()
    expected=next((g['sha256'] for g in data['grids'] if g['name']==name),None)
    if name=='wavefunction.molden':expected=data.get('molden',{}).get('sha256')
    if expected and hashlib.sha256(blob).hexdigest()!=expected:raise ValueError('Visualization artifact hash changed')
    return blob
