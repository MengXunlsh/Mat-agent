"""Strict finite-molecule DFT inputs shared by the web adapter and compute worker."""
import math

ELEMENTS = ('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn '
 'Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd '
 'Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th '
 'Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og').split()
METHODS = {'pbe', 'b3lyp', 'wb97x'}
BASES = {'sto-3g', 'def2-svp', 'def2-tzvp'}

def validate_task(task):
    if isinstance(task,dict) and task.get('backend')=='qe':
        from highzyme.compute.qe_backend import validate_qe_task
        return validate_qe_task(task)
    required={'structure','calculation','method','basis','label'}
    if not isinstance(task,dict) or not required<=set(task) or set(task)-required-{'visualization'}:
        raise ValueError('DFT task requires exactly structure, calculation, method, basis and label')
    if task['calculation'] not in {'energy','optimize'} or task['method'] not in METHODS or task['basis'] not in BASES:
        raise ValueError('Choose a registered finite-molecule calculation, functional and basis')
    if not isinstance(task['label'],str) or not 1<=len(task['label'].strip())<=200:
        raise ValueError('A descriptive calculation label is required')
    s=task['structure']
    if not isinstance(s,dict) or set(s)!={'symbols','positions_angstrom','charge','multiplicity','source'}:
        raise ValueError('Supply explicit symbols, positions_angstrom, charge, multiplicity and structure source; periodic cells are not supported by this backend')
    symbols,positions=s['symbols'],s['positions_angstrom']
    if not isinstance(symbols,list) or not 1<=len(symbols)<=32 or any(x not in ELEMENTS for x in symbols):
        raise ValueError('Supply 1–32 explicit valid element symbols')
    if not isinstance(positions,list) or len(positions)!=len(symbols):
        raise ValueError('Each atom requires one Cartesian position in angstrom')
    for p in positions:
        if not isinstance(p,list) or len(p)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1000 for x in p):
            raise ValueError('Coordinates must be bounded finite triples')
    if any(sum((a-b)**2 for a,b in zip(p,q))<.09 for i,p in enumerate(positions) for q in positions[i+1:]):
        raise ValueError('Atoms closer than 0.3 angstrom require structure review')
    if type(s['charge']) is not int or abs(s['charge'])>12 or type(s['multiplicity']) is not int or not 1<=s['multiplicity']<=9:
        raise ValueError('Explicit bounded integer charge and multiplicity are required')
    electrons=sum(ELEMENTS.index(x)+1 for x in symbols)-s['charge']
    if electrons<=0 or electrons<s['multiplicity']-1 or (electrons-(s['multiplicity']-1))%2:
        raise ValueError('Charge, electron count and spin multiplicity are inconsistent')
    if not isinstance(s['source'],str) or not 1<=len(s['source'].strip())<=2000:
        raise ValueError('Structure source or explicitly constructed-model basis is required')
    if 'visualization' in task:
        validate_visualization(task['visualization'],positions)
    return task


def validate_visualization(settings,positions):
    """Bound the optional electronic-grid export before accepting a calculation."""
    if not isinstance(settings,dict) or set(settings)!={'properties','grid_spacing_bohr','padding_bohr'}:
        raise ValueError('Visualization requires properties, grid_spacing_bohr and padding_bohr')
    props=settings['properties']
    if not isinstance(props,list) or not props or any(not isinstance(p,str) for p in props) or len(props)!=len(set(props)) or any(
            p not in {'electron_density','spin_density','frontier_orbitals'} for p in props):
        raise ValueError('Choose registered electronic visualization properties')
    spacing,padding=settings['grid_spacing_bohr'],settings['padding_bohr']
    if type(spacing) not in (int,float) or not math.isfinite(spacing) or not .2<=spacing<=.6:
        raise ValueError('Visualization grid spacing must be 0.2–0.6 bohr')
    if type(padding) not in (int,float) or not math.isfinite(padding) or not 3<=padding<=8:
        raise ValueError('Visualization padding must be 3–8 bohr')
    dimensions=[math.ceil(((max(p[k] for p in positions)-min(p[k] for p in positions))/.529177210903+2*padding)/spacing)+3 for k in range(3)]
    if math.prod(dimensions)>500000:
        raise ValueError('Requested electronic grid exceeds the local export limit; use a coarser grid or smaller padding')
    return settings
