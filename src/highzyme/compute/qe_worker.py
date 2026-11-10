"""One predeclared QE calculation, with retained inputs/logs and convergence gating."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from highzyme.compute.qe_backend import validate_qe_task,build_qe_input,pseudopotentials
from highzyme.compute.dft_jobs import clean_environment

def main():
    p=argparse.ArgumentParser();p.add_argument('--job',required=True);p.add_argument('--threads',type=int,required=True);p.add_argument('--memory-mb',type=int,required=True);args=p.parse_args()
    folder=Path(args.job).resolve();raw=(folder/'request.json').read_bytes();task=validate_qe_task(json.loads(raw));cfg=json.loads((folder/'backend.json').read_text())
    pseudo_dir=Path(cfg['pseudo_dir']);executable=Path(cfg['executable'])
    manifest=[]
    for el in sorted(set(task['structure']['symbols'])):
        f=pseudo_dir/pseudopotentials(task)[el];r=f.read_bytes();manifest.append({'element':el,'filename':f.name,'sha256':hashlib.sha256(r).hexdigest()})
        header=r[:16000].decode('utf8',errors='replace')
        if not (re.search(r'element\s*=\s*["\']\s*'+el+r'\s*["\']',header) or re.search(r'^\s*'+el+r'\s+Element\s*$',header,re.M)):raise ValueError('Pseudopotential element mismatch')
    (folder/'qe.in').write_text(build_qe_input(task,pseudo_dir),encoding='ascii')
    from ase import Atoms
    from ase.io import write,read
    s=task['structure'];atoms=Atoms(s['symbols'],positions=s['positions_angstrom'],cell=s['cell_angstrom'],pbc=True)
    write(folder/'input.xyz',atoms);write(folder/'input.cif',atoms)
    env=clean_environment(sys.executable);env['PATH']=str(executable.parent)+os.pathsep+env['PATH'];env.update(OMP_NUM_THREADS=str(args.threads),MKL_NUM_THREADS=str(args.threads),OPENBLAS_NUM_THREADS='1')
    start=time.time()
    print('Running registered local QE backend',flush=True)
    with (folder/'qe.out').open('wb') as out:
        child=subprocess.Popen([str(executable),'-in','qe.in'],cwd=folder,stdout=out,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        code=child.wait()
    text=(folder/'qe.out').read_text('utf8',errors='replace')
    if code or 'JOB DONE.' not in text or 'convergence NOT achieved' in text or not re.search(r'convergence has been achieved',text):raise ValueError('QE did not converge and finish; inspect retained qe.out')
    energy=re.findall(r'!\s+total energy\s*=\s*([-+\d.Ee]+)\s+Ry',text)
    if not energy:raise ValueError('No converged total energy found')
    if task['calculation']=='optimize' and 'End of BFGS Geometry Optimization' not in text:raise ValueError('Geometry relaxation did not converge')
    final=read(folder/'qe.out',format='espresso-out',index=-1);write(folder/'final.xyz',final);write(folder/'final.cif',final)
    ry=float(energy[-1]);version=re.search(r'Program PWSCF\s+v\.(\S+)',text);mags=re.findall(r'total magnetization\s*=\s*([-+\d.]+)',text)
    result={'backend':'qe','version':version[1] if version else 'unknown','request_sha256':hashlib.sha256(raw).hexdigest(),
        'energy_Ry':ry,'energy_hartree':ry/2,'energy_eV':ry*13.605693122994,'method':'pbe','basis':'plane waves / '+task['settings'].get('pseudopotential_family','pslibrary-pbe-paw'),
        'charge':s['charge'],'multiplicity':None,'scf_converged':True,'optimization_converged':task['calculation']=='optimize',
        'symbols':final.get_chemical_symbols(),'positions_angstrom':final.positions.tolist(),'cell_angstrom':final.cell.array.tolist(),
        'total_magnetization_muB':float(mags[-1]) if mags else None,'settings':task['settings'],'pseudopotentials':manifest,
        'wall_seconds':time.time()-start,'source':s['source'],'input_structure_file_id':s.get('file_id'),
        'qualification':'Local periodic single-point/relaxation with explicitly declared settings; not a converged spin-ground-state search or original VASP reproduction.'}
    tmp=folder/'result.tmp';tmp.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf8');tmp.replace(folder/'result.json')
    print('Converged result saved',flush=True)

if __name__=='__main__':main()
