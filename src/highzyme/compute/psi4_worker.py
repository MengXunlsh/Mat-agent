"""Run one validated job in the isolated Psi4 environment; not an arbitrary-code runner."""
from pathlib import Path
import argparse,json,os,sys,time,hashlib
import faulthandler
faulthandler.dump_traceback_later(45,repeat=False)

if os.name=='nt':
    _dll_handles=[os.add_dll_directory(str(p)) for p in [Path(sys.prefix)/'Library/bin',Path(sys.prefix)/'DLLs'] if p.is_dir()]
from dft_schema import validate_task

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--job',required=True)
    parser.add_argument('--threads',type=int,required=True);parser.add_argument('--memory-mb',type=int,required=True)
    args=parser.parse_args();folder=Path(args.job).resolve()
    if not 1<=args.threads<=4 or not 512<=args.memory_mb<=4096:raise ValueError('Compute resource bounds rejected')
    raw=(folder/'request.json').read_bytes();task=validate_task(json.loads(raw))
    print('Loading local Psi4 and ASE',flush=True)
    import psi4,ase
    print('DFT libraries loaded',flush=True)
    from ase import Atoms
    from ase.io import write
    structure=task['structure'];atoms=Atoms(structure['symbols'],positions=structure['positions_angstrom'])
    write(folder/'input.xyz',atoms)
    scratch=folder/'scratch';scratch.mkdir(exist_ok=True)
    os.environ['PSI_SCRATCH']=str(scratch)
    psi4.core.IOManager.shared_object().set_default_path(str(scratch))
    psi4.set_num_threads(args.threads);psi4.set_memory(f'{args.memory_mb} MB')
    psi4.core.set_output_file(str(folder/'psi4.out'),False)
    geometry=f"{structure['charge']} {structure['multiplicity']}\n"+'\n'.join(
        f'{symbol} {p[0]:.14g} {p[1]:.14g} {p[2]:.14g}' for symbol,p in zip(atoms.get_chemical_symbols(),atoms.positions))
    molecule=psi4.geometry(geometry+'\nunits angstrom\nsymmetry c1\nno_reorient\nno_com')
    psi4.set_options({'basis':task['basis'],'reference':'rks' if structure['multiplicity']==1 else 'uks',
        'scf_type':'df','e_convergence':1e-8,'d_convergence':1e-8,'maxiter':100,
        'dft_radial_points':75,'dft_spherical_points':302})
    start=time.monotonic()
    if task['calculation']=='optimize':
        energy,wfn=psi4.optimize(task['method'],molecule=molecule,return_wfn=True)
    else:energy,wfn=psi4.energy(task['method'],molecule=molecule,return_wfn=True)
    faulthandler.cancel_dump_traceback_later()
    final=wfn.molecule();coordinates=final.geometry().to_array()*psi4.constants.bohr2angstroms
    atoms.set_positions(coordinates);write(folder/'final.xyz',atoms)
    if not all(map(lambda v:__import__('math').isfinite(float(v)),[energy])):raise ValueError('Nonfinite energy rejected')
    data={'energy_hartree':float(energy),'energy_eV':float(energy)*psi4.constants.hartree2ev,
        'symbols':atoms.get_chemical_symbols(),'positions_angstrom':coordinates.tolist(),
        'charge':structure['charge'],'multiplicity':structure['multiplicity'],
        'method':task['method'],'basis':task['basis'],'nbf':wfn.basisset().nbf(),'nalpha':wfn.nalpha(),'nbeta':wfn.nbeta(),
        'scf_converged':True,'optimization_converged':True if task['calculation']=='optimize' else None,
        'psi4_version':psi4.__version__,'ase_version':ase.__version__,'elapsed_seconds':time.monotonic()-start,
        'effective_electron_count':wfn.nalpha()+wfn.nbeta(),
        'ecp_core_electron_count':int(sum(atoms.numbers)-structure['charge']-wfn.nalpha()-wfn.nbeta()),
        'settings':{'reference':'rks' if structure['multiplicity']==1 else 'uks','scf_type':'df',
            'e_convergence':1e-8,'d_convergence':1e-8,'max_scf_iterations':100,
            'dft_radial_points':75,'dft_spherical_points':302,'threads':args.threads,'memory_mb':args.memory_mb},
        'structure_source':structure['source'],'request_sha256':hashlib.sha256(raw).hexdigest(),
        'interpretation':'Finite isolated molecule/cluster DFT; no periodic surface, solvent, D3 correction or paper reproduction is implied.'}
    if task.get('visualization'):
        try:
            from dft_visualization import export_psi4
            data['visualization']=export_psi4(psi4,wfn,folder,task['visualization'])
        except Exception as exc:
            data['visualization']={'status':'FAILED','reason':type(exc).__name__+': electronic-grid export failed; converged energy retained.'}
            print('Visualization export failed: '+str(exc),flush=True)
    temp=folder/'result.tmp';temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),'utf8')
    temp.replace(folder/'result.json')
    print(json.dumps({'status':'COMPLETED','energy_hartree':float(energy)}),flush=True)

if __name__=='__main__':main()
