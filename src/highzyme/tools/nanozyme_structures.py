"""Nanozyme inputs: RDKit molecular graphs and Gemmi crystal/macromolecule sites."""
from collections import Counter
import io
import math
from pathlib import Path

def _sites(symbols,positions,labels,occupancies,**extra):
    if not 1<=len(symbols)<=20000 or len(positions)!=len(symbols):raise ValueError('请选择包含1—20000个原子位点的单一结构。')
    if any(not math.isfinite(v) for p in positions for v in p) or any(not 0<=o<=1 for o in occupancies):raise ValueError('结构坐标或占位率无效。')
    weighted={}
    for s,o in zip(symbols,occupancies):weighted[s]=weighted.get(s,0)+o
    return {'kind':'structure','symbols':symbols,'positions_angstrom':positions,'atom_labels':labels,
        'occupancies':occupancies,'site_occupancy_counts':weighted,'periodic_cell_present':False,
        'boundary_conditions_confirmed':False,'charge':None,'multiplicity':None,'notes':[],**extra}

def crystal(raw):
    import gemmi
    doc=gemmi.cif.read_string(raw.decode('utf-8-sig'))
    blocks=[b for b in doc if b.find_values('_atom_site_fract_x') or b.find_values('_atom_site.Cartn_x')]
    if len(blocks)!=1:raise ValueError('请选择含单一结构数据块的 CIF 文件。')
    block=blocks[0]
    if block.find_values('_atom_site.Cartn_x'):return macromolecule(gemmi.make_structure_from_block(block))
    model=gemmi.make_small_structure_from_block(block);model.setup_cell_images()
    if len(model.sites)*(len(model.cell.images)+1)>20000:raise ValueError('晶胞展开超过20000个位点，请选择较小的结构模型。')
    sites=list(model.get_all_unit_cell_sites())
    if not sites:raise ValueError('CIF 中没有可解析的原子位点。')
    cell=model.cell
    matrix=[[v.x,v.y,v.z] for v in [cell.orth.mat.multiply(gemmi.Vec3(1,0,0)),cell.orth.mat.multiply(gemmi.Vec3(0,1,0)),cell.orth.mat.multiply(gemmi.Vec3(0,0,1))]]
    positions=[cell.orthogonalize(s.fract) for s in sites]
    return _sites([s.element.name for s in sites],[[p.x,p.y,p.z] for p in positions],[s.label for s in sites],[s.occ for s in sites],
        cell_angstrom=matrix,cell_parameters=[cell.a,cell.b,cell.c,cell.alpha,cell.beta,cell.gamma],
        fractional_positions=[[s.fract.x,s.fract.y,s.fract.z] for s in sites],periodic_cell_present=True,
        space_group=model.spacegroup_hm,parser='Gemmi '+gemmi.__version__,coordinate_basis='symmetry-expanded unit-cell sites')

def macromolecule(structure):
    import gemmi
    if len(structure)!=1:raise ValueError('请选择单一 MODEL 的结构文件。')
    symbols=[];positions=[];labels=[];occupancies=[];residues=0;chains=0
    for chain in structure[0]:
        chains+=1
        for residue in chain:
            residues+=1
            for atom in residue:
                if len(symbols)>=20000:raise ValueError('结构超过20000个位点，请选择需要的链或片段。')
                symbols.append(atom.element.name);positions.append([atom.pos.x,atom.pos.y,atom.pos.z]);occupancies.append(atom.occ)
                labels.append('/'.join([chain.name,str(residue.seqid),residue.name,atom.name,atom.altloc.strip('\x00')]))
    return _sites(symbols,positions,labels,occupancies,chain_count=chains,residue_count=residues,
        parser='Gemmi '+gemmi.__version__,coordinate_basis='reported macromolecular atom sites; alternative locations retained',
        notes=['坐标组成按文件中已给出的原子位点统计，不补齐缺失原子或氢。'])

def molecular(raw,fmt):
    from rdkit import Chem
    molecules=list(Chem.ForwardSDMolSupplier(io.BytesIO(raw),removeHs=False)) if fmt=='sdf' else [Chem.MolFromMolBlock(raw.decode('utf-8-sig'),removeHs=False)]
    if len(molecules)!=1 or molecules[0] is None:raise ValueError('请选择一个有效的分子结构。')
    mol=molecules[0]
    if not mol.GetNumConformers():raise ValueError('分子文件没有原子坐标。')
    conf=mol.GetConformer();pos=conf.GetPositions().tolist()
    return _sites([a.GetSymbol() for a in mol.GetAtoms()],pos,[a.GetSymbol()+str(a.GetIdx()+1) for a in mol.GetAtoms()],[1.]*mol.GetNumAtoms(),
        smiles=Chem.MolToSmiles(mol),charge=Chem.GetFormalCharge(mol),coordinate_dimension=3 if conf.Is3D() else 2,parser='RDKit',
        notes=[] if conf.Is3D() else ['文件为二维分子结构，坐标不作为已建立的三维构型。'])

def parse_nanozyme_structure(raw,filename):
    fmt=Path(filename).suffix.lower().lstrip('.')
    try:
        if fmt in {'cif','mmcif'}:return crystal(raw)
        if fmt=='pdb':
            import gemmi
            return macromolecule(gemmi.read_pdb_string(raw.decode('utf-8-sig')))
        if fmt in {'mol','sdf'}:return molecular(raw,fmt)
        if fmt in {'xyz','extxyz','vasp','poscar','contcar'} or Path(filename).name.upper() in {'POSCAR','CONTCAR'}:
            from ase.io import read
            import ase
            kind='vasp' if fmt in {'vasp','poscar','contcar'} or Path(filename).name.upper() in {'POSCAR','CONTCAR'} else 'extxyz'
            models=read(io.StringIO(raw.decode('utf-8-sig')),format=kind,index=':')
            if len(models)!=1:raise ValueError('Select a single coordinate model')
            atoms=models[0]
            result=_sites(atoms.get_chemical_symbols(),atoms.positions.tolist(),
                          [str(i+1) for i in range(len(atoms))],[1.0]*len(atoms),
                          parser='ASE '+ase.__version__,coordinate_basis='supplied atom coordinates',
                          periodic_cell_present=bool(atoms.cell.rank),boundary_conditions_confirmed=kind=='vasp' or bool(atoms.cell.rank),
                          periodic_axes=atoms.pbc.tolist())
            if atoms.cell.rank:result['cell_angstrom']=atoms.cell.array.tolist()
            return result
    except (RuntimeError,UnicodeError) as exc:raise ValueError('结构文件解析失败，请核对格式与结构数据。') from exc
    raise ValueError('结构格式无效。')

def identity_from_file(context,ident):
    from rdkit import Chem
    from highzyme.tools.file_inputs import parse,read_file,check_tool_format
    from highzyme.tools.chemistry import molecule_info
    row,_=read_file(context,ident);check_tool_format(row['filename'],'chemical_identity');d=parse(context,ident)
    if d['kind']!='structure':raise ValueError('请选择分子、晶体或原子坐标文件。')
    if d.get('smiles'):data=molecule_info(d['smiles'])
    else:
        counts=d.get('site_occupancy_counts',dict(Counter(d['symbols'])))
        table=Chem.GetPeriodicTable()
        data={'element_counts':counts,'coordinate_mass_da':sum(table.GetAtomicWeight(s)*n for s,n in counts.items()),
            'mass_basis':'occupancy-weighted atom inventory in supplied coordinates','structure_available':True}
    data.update(atom_count=d['atom_count'],periodic_cell_present=d['periodic_cell_present'],
        structure_type='晶体 / 周期结构' if d['periodic_cell_present'] else '大分子坐标' if d.get('residue_count') else '分子 / 团簇',
        **{k:d[k] for k in ('cell_parameters','chain_count','residue_count','coordinate_dimension','space_group') if k in d})
    return {'status':'COMPLETED','data':data,'source':{'kind':'uploaded_structure','file_id':ident,'filename':d['filename'],'sha256':d['source_sha256']},
        'method':d.get('parser','ASE / explicit supplied coordinates'),'limitations':d.get('notes',[])}
