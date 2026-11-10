"""Registered periodic Quantum ESPRESSO configuration and bounded inputs."""
from pathlib import Path
from dataclasses import dataclass
import math,os
from highzyme.infrastructure.runtime_paths import PROJECT_ROOT
from highzyme.compute.dft_schema import ELEMENTS

PSEUDOS={'H':'H.pbe-kjpaw_psl.1.0.0.UPF','C':'C.pbe-n-kjpaw_psl.1.0.0.UPF',
 'N':'N.pbe-n-kjpaw_psl.1.0.0.UPF','O':'O.pbe-n-kjpaw_psl.1.0.0.UPF',
 'Co':'Co.pbe-spn-kjpaw_psl.0.3.1.UPF','Pt':'Pt.pbe-n-kjpaw_psl.1.0.0.UPF'}
USPP={el:name.replace('-kjpaw','-rrkjus') for el,name in PSEUDOS.items()}
PSEUDO_FAMILIES={'pslibrary-pbe-paw':PSEUDOS,'pslibrary-pbe-uspp':USPP}
PSEUDO_FAMILIES['gbrv-pbe-uspp']={'H':'h_pbe_v1.4.uspp.F.UPF','C':'c_pbe_v1.2.uspp.F.UPF','N':'n_pbe_v1.2.uspp.F.UPF','O':'o_pbe_v1.2.uspp.F.UPF','Co':'co_pbe_v1.2.uspp.F.UPF','Pt':'pt_pbe_v1.4.uspp.F.UPF'}
def pseudopotentials(task):return PSEUDO_FAMILIES[task['settings'].get('pseudopotential_family','pslibrary-pbe-paw')]

@dataclass(frozen=True)
class QEConfig:
    work_dir:Path
    python:Path
    executable:Path
    pseudo_dir:Path
    threads:int=4
    memory_mb:int=16384
    timeout_seconds:int=7200
    backend:str='qe'

    def __post_init__(self):
        for key in ('work_dir','python','executable','pseudo_dir'):object.__setattr__(self,key,Path(getattr(self,key)).resolve())
        if not 1<=self.threads<=8 or not 1024<=self.memory_mb<=16384 or not 1<=self.timeout_seconds<=14400:raise ValueError('Periodic compute resource bounds exceeded')

    @classmethod
    def configured(cls):
        from highzyme.compute.dft_jobs import LocalDFTConfig
        base=LocalDFTConfig.configured()
        return cls(base.work_dir,base.python,Path(os.environ.get('HIGHZYME_QE_EXECUTABLE',PROJECT_ROOT/'.tools/dft/qe/bin/pw.exe')),
            Path(os.environ.get('HIGHZYME_QE_PSEUDO_DIR',PROJECT_ROOT/'.tools/dft/pseudopotentials')),
            int(os.environ.get('HIGHZYME_QE_THREADS','4')),int(os.environ.get('HIGHZYME_QE_MEMORY_MB','16384')),
            int(os.environ.get('HIGHZYME_QE_TIMEOUT_SECONDS','7200')))

    def public(self):
        return {'backend':'qe','available':self.executable.is_file() and self.python.is_file(),'system':'local','paid_compute':False,
            'supported_system':'explicit periodic cell','periodic_supported':True,'max_atoms':160,'max_concurrent_jobs':1,
            'threads':self.threads,'memory_mb':self.memory_mb,'memory_policy':'QE estimate gate; Windows owned-process job memory cap; Linux requires deployment cgroup limit',
            'timeout_seconds':self.timeout_seconds,'registered_elements':list(PSEUDOS),'pseudopotential_families':list(PSEUDO_FAMILIES),'pseudopotentials_ready':all((self.pseudo_dir/n).is_file() for family in PSEUDO_FAMILIES.values() for n in family.values())}

def validate_qe_task(task):
    if not isinstance(task,dict) or set(task)!={'backend','label','calculation','method','structure','settings'}:raise ValueError('Periodic task requires backend,label,calculation,method,structure,settings')
    if task['backend']!='qe' or task['calculation'] not in {'energy','optimize'} or task['method']!='pbe':raise ValueError('Registered periodic backend supports PBE single-point or fixed-cell relaxation')
    if not isinstance(task['label'],str) or not 1<=len(task['label'])<=200:raise ValueError('Calculation label required')
    s=task['structure'];required={'symbols','positions_angstrom','cell_angstrom','charge','source'}
    if not isinstance(s,dict) or not required<=set(s) or set(s)-required-{'file_id','file_sha256','atom_labels'}:raise ValueError('Explicit full periodic structure required')
    symbols=s['symbols'];p=s['positions_angstrom'];cell=s['cell_angstrom']
    if not isinstance(symbols,list) or not 1<=len(symbols)<=160 or any(x not in PSEUDOS for x in symbols):raise ValueError('Periodic structure requires 1–160 atoms with registered pseudopotentials')
    def triples(rows,n):
        return isinstance(rows,list) and len(rows)==n and all(isinstance(v,list) and len(v)==3 and all(type(x) in (int,float) and math.isfinite(x) and abs(x)<=1000 for x in v) for v in rows)
    if not triples(p,len(symbols)) or not triples(cell,3):raise ValueError('Finite explicit coordinates and 3x3 cell required')
    import numpy as np
    a=np.asarray(cell)
    if abs(np.linalg.det(a))<10 or any(not 3<=np.linalg.norm(v)<=60 for v in a):raise ValueError('Cell volume/length outside local bounds')
    inv=np.linalg.inv(a)
    for i,x in enumerate(p):
        for y in p[i+1:]:
            frac=(np.asarray(x)-y)@inv;frac-=np.round(frac)
            if np.linalg.norm(frac@a)<.3:raise ValueError('Periodic atoms overlap within 0.3 angstrom')
    if type(s['charge']) is not int or abs(s['charge'])>12 or not isinstance(s['source'],str) or not s['source'] or len(s['source'])>2000:raise ValueError('Explicit bounded charge and source required')
    settings=task['settings'];keys={'ecutwfc_Ry','ecutrho_Ry','kpoints','degauss_Ry','conv_thr_Ry','electron_maxstep','starting_magnetization','dispersion'}
    if not isinstance(settings,dict) or not keys<=set(settings) or set(settings)-keys-{'pseudopotential_family'}:raise ValueError('Supply all declared periodic calculation settings')
    if settings.get('pseudopotential_family','pslibrary-pbe-paw') not in PSEUDO_FAMILIES:raise ValueError('Choose registered PAW or ultrasoft PBE pseudopotentials')
    def num(key,lo,hi):
        x=settings[key]
        if type(x) not in (int,float) or not math.isfinite(x) or not lo<=x<=hi:raise ValueError('Invalid periodic setting '+key)
        return x
    w=num('ecutwfc_Ry',20,100);r=num('ecutrho_Ry',80,1000)
    if not 4*w<=r<=12*w:raise ValueError('Density cutoff must be 4–12 times wavefunction cutoff')
    num('degauss_Ry',.001,.05);num('conv_thr_Ry',1e-10,1e-4)
    k=settings['kpoints']
    if not isinstance(k,list) or len(k)!=3 or any(type(x) is not int or not 1<=x<=4 for x in k) or math.prod(k)>8:raise ValueError('Bounded 3D k-point grid required')
    if type(settings['electron_maxstep']) is not int or not 1<=settings['electron_maxstep']<=200:raise ValueError('SCF iteration bound required')
    mags=settings['starting_magnetization']
    if not isinstance(mags,dict) or not set(mags)<=set(symbols) or any(type(x) not in (int,float) or not math.isfinite(x) or not -1<=x<=1 for x in mags.values()):raise ValueError('Declare element-specific starting magnetization fractions')
    if settings['dispersion'] not in {'none','dft-d3'}:raise ValueError('Use none or dft-d3')
    return task

def build_qe_input(task,pseudo_dir):
    validate_qe_task(task)
    from ase.data import atomic_masses,atomic_numbers
    s=task['structure'];v=task['settings'];elements=list(dict.fromkeys(s['symbols']))
    lines=['&CONTROL'," calculation = 'scf'," if task['calculation']=='energy' else " calculation = 'relax',",
        " prefix = 'highzyme',", " pseudo_dir = '"+str(pseudo_dir).replace('\\','/')+"',", " outdir = './scratch',", " disk_io = 'medium',",' tprnfor = .true.,','/','&SYSTEM',
        f" ibrav = 0, nat = {len(s['symbols'])}, ntyp = {len(elements)},",f" ecutwfc = {v['ecutwfc_Ry']}, ecutrho = {v['ecutrho_Ry']},",
        f" tot_charge = {s['charge']}, nspin = 2,", " occupations = 'smearing', smearing = 'mv',",f" degauss = {v['degauss_Ry']},"]
    for i,el in enumerate(elements,1):lines.append(f" starting_magnetization({i}) = {v['starting_magnetization'].get(el,0.)},")
    if v['dispersion']=='dft-d3':lines.append(" vdw_corr = 'dft-d3', dftd3_version = 3,")
    lines+=['/','&ELECTRONS',f" conv_thr = {v['conv_thr_Ry']}, electron_maxstep = {v['electron_maxstep']},",' mixing_beta = 0.15, mixing_ndim = 4,'," diagonalization = 'cg',",'/']
    if task['calculation']=='optimize':lines+=['&IONS'," ion_dynamics = 'bfgs',",'/']
    pseudos=pseudopotentials(task)
    lines+=['ATOMIC_SPECIES']+[f'{el} {atomic_masses[atomic_numbers[el]]:.8f} {pseudos[el]}' for el in elements]
    lines+=['CELL_PARAMETERS angstrom']+[' '.join(f'{x:.10f}' for x in p) for p in s['cell_angstrom']]
    lines+=['ATOMIC_POSITIONS angstrom']+[el+' '+' '.join(f'{x:.10f}' for x in p) for el,p in zip(s['symbols'],s['positions_angstrom'])]
    lines+=['K_POINTS gamma'] if v['kpoints']==[1,1,1] else ['K_POINTS automatic',' '.join(map(str,v['kpoints']))+' 0 0 0']
    return '\n'.join(lines)+'\n'
