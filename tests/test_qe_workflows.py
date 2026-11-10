import json
from pathlib import Path
import shutil
import tempfile
import unittest
import subprocess
import sys
from copy import deepcopy

import numpy as np
from ase import Atoms
from ase.io.cube import write_cube
from ase.units import Bohr

from ase.io import read, write
from ase.units import Rydberg

from highzyme.compute.qe_calculation import prepare as prepare_pw
from highzyme.compute.qe_workflows import prepare, collect, energy_combinations
from highzyme.compute.workflow_runner import build_runner
from highzyme.compute.qe_analysis import electronic_result, charge_result, thermal_corrections

ROOT = Path(__file__).resolve().parents[1]


class QeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copyfile(ROOT / 'examples/general-research/qe-smoke/silicon.extxyz', self.root / 'silicon.extxyz')
        (self.root / 'si.upf').write_text('<UPF><PP_HEADER element="Si" z_valence="4" /></UPF>')
        self.config = dict(method='convergence', models=[dict(id='silicon', structure_file='silicon.extxyz')], pseudopotentials={'Si': 'si.upf'},
                           parameters=dict(calculation='scf', ecutwfc=30, kpoints=[1, 1, 1]),
                           convergence=dict(parameter='ecutwfc', values=[20, 30], tolerance_eV_atom=.01))

    def tearDown(self):
        self.temporary.cleanup()

    def test_variable_cell_and_constraints_use_real_ase_writer(self):
        result = prepare_pw(dict(directory=str(self.root / 'vc'), structure_file=str(self.root / 'silicon.extxyz'),
                                 pseudopotentials={'Si': str(self.root / 'si.upf')}, parameters={**self.config['parameters'], 'calculation': 'vc-relax', 'fixed_atoms': [0]}))
        text = (self.root / 'vc/qe.in').read_text()
        self.assertIn('cell_dynamics', text)
        self.assertTrue(result['request']['parameters']['system']['nosym'])
        self.assertEqual(result['request']['parameters']['calculation'], 'vc-relax')
        atoms = read(self.root / 'vc/qe.in', format='espresso-in')
        self.assertTrue(atoms.constraints)

    def test_convergence_prepares_stages_and_collects_saved_qe_output(self):
        folder = self.root / 'workflow'
        result = prepare(dict(root=str(self.root), directory=str(folder), config=self.config))
        self.assertEqual(result['required_programs'], ['pw'])
        manifest = result['manifest']
        source = (ROOT / 'tests/fixtures/qe-silicon-scf.out').read_text()
        for i, stage in enumerate(manifest['stages']):
            self.assertEqual(read(folder / stage['folder'] / 'qe.in', format='espresso-in').get_chemical_formula(), 'Si2')
            (folder / stage['folder'] / 'qe.out').write_text(source.replace('-14.50260042', str(-14.50260042 + .0001 * (1 - i))))
        (folder / 'workflow-status.json').write_text(json.dumps(dict(status='completed')))
        result = collect(dict(directory=str(folder), job=dict(status='completed')))
        self.assertEqual(result['result']['converged_setting'], 20)
        self.assertAlmostEqual(result['result']['tables'][0]['rows'][0]['delta_eV_atom'], .0001 * Rydberg / 2)
        self.assertTrue((folder / 'figure-1.svg').exists())

    def test_energy_combinations_check_stoichiometry_and_keep_sign(self):
        manifest = dict(analysis=dict(combinations=[dict(id='binding', coefficients=dict(combined=1, surface=-1, molecule=-1))]))
        models = dict(combined=dict(energy_eV=-14., symbols=['Si', 'H']), surface=dict(energy_eV=-10., symbols=['Si']), molecule=dict(energy_eV=-3., symbols=['H']))
        self.assertEqual(energy_combinations(manifest, models)[0]['energy_eV'], -1.)
        models['molecule']['symbols'] = ['H', 'H']
        with self.assertRaisesRegex(ValueError, 'element-balanced'):
            energy_combinations(manifest, models)

    def test_electronic_workflow_reuses_scratch_and_reads_numeric_spectra(self):
        config = deepcopy(self.config)
        config['method'] = 'electronic-structure'
        config['electronic'] = dict(kpoints=[2,2,2], pdos=True, pdos_groups=[dict(id='si-p', atoms=[0], orbital='p', window_eV=[-1,1])],
                                    bands=dict(points=[[0,0,0],[.5,0,0]], labels=['G','X'], points_per_segment=2))
        folder = self.root/'electronic'
        manifest = prepare(dict(root=str(self.root), directory=str(folder), config=config))['manifest']
        self.assertEqual([s['program'] for s in manifest['stages']], ['pw','pw','dos','projwfc','pw','bands'])
        self.assertIn('../shared/silicon', (folder/'density-states/qe.in').read_text())
        (folder/'density-states/qe.out').write_text('the Fermi energy is 2.0 ev')
        np.savetxt(folder/'dos/dos.dat', [[1,1,0],[2,2,1],[3,1,2]])
        np.savetxt(folder/'pdos/pdos.pdos_atm#1(Si)_wfc#1(p)', [[1,1],[2,2],[3,1]])
        (folder/'bands/bands.dat.gnu').write_text('0 1\n0.25 2\n0.5 3\n\n0 2\n0.25 3\n0.5 4\n')
        result = dict(charts=[],tables=[])
        electronic_result(folder,manifest,result)
        self.assertEqual(result['charts'][0]['series'][0]['x'], [-1.,0.,1.])
        self.assertAlmostEqual(result['tables'][1]['rows'][0]['center_relative_eV'], 0.)
        self.assertEqual(result['charts'][-1]['x_ticks']['positions'], [0.,.5])

    def test_charge_density_preserves_units_grids_and_bader_sign(self):
        folder=self.root/'charge'; folder.mkdir()
        atoms=Atoms('H',positions=[[1,1,1]],cell=[2,2,2],pbc=True)
        for model, value in [('combined',2.),('fragment',1.)]:
            (folder/('density-'+model)).mkdir()
            with (folder/('density-'+model)/'density.cube').open('w') as stream:
                write_cube(stream,atoms,np.full((4,4,4),value))
        (folder/'bader-combined').mkdir()
        (folder/'bader-combined/ACF.dat').write_text(' 1 1 1 1 0.8 0.1 1.0\n')
        manifest=dict(models={'combined':dict(symbols=['H']),'fragment':dict(symbols=['H'])},analysis=dict(options=dict(coefficients={'combined':1,'fragment':-1},display_model='combined',bader_models=['combined']),reference_electrons={'combined':{'H':1}}))
        result=dict(charts=[],tables=[])
        files=charge_result(folder,manifest,result)
        self.assertAlmostEqual(result['conditions']['integrated_difference_e'],8/Bohr**3,places=4)
        self.assertAlmostEqual(result['tables'][-1]['rows'][0]['net_charge_e'],.2)
        self.assertTrue((folder/files['charge_volume']).exists())
        with (folder/'density-fragment/density.cube').open('w') as stream:
            write_cube(stream,atoms,np.zeros((3,3,3)))
        with self.assertRaisesRegex(ValueError,'grids'):
            charge_result(folder,manifest,dict(charts=[],tables=[]))

    def test_thermal_sources_and_balanced_states_are_required_before_submission(self):
        config=deepcopy(self.config)
        config.update(method='reaction-energy',energy_kind='free-energy',thermochemistry=dict(temperature_K=298.15,pressure_Pa=100000),
                      states=[dict(id='start',coefficients={'silicon':1}),dict(id='end',coefficients={'silicon':2})],reference_state='start')
        config['models'][0].update(thermal_correction_eV=.2,thermal_source='reference correction',corrections=[dict(value_eV=.1,source='standard-state correction')])
        with self.assertRaisesRegex(ValueError,'element-balanced'):
            prepare(dict(root=str(self.root),directory=str(self.root/'unbalanced'),config=config))
        config['states'][1]['coefficients']['silicon']=1
        manifest=prepare(dict(root=str(self.root),directory=str(self.root/'thermal'),config=config))['manifest']
        correction,record=thermal_corrections(self.root/'thermal',manifest,{})
        self.assertAlmostEqual(correction['silicon'],.3)
        self.assertEqual(record['silicon']['method'],'supplied')

    def test_neb_uses_ordered_constrained_images_and_native_neb_input(self):
        config=deepcopy(self.config)
        config['method']='neb'
        config['models'].append(dict(id='final',structure_file='silicon.extxyz'))
        config['parameters']['fixed_atoms']=[0]
        config['neb']=dict(initial='silicon',final='final',images=3,force_threshold_eV_A=.05,interpolation='linear')
        folder=self.root/'neb'
        manifest=prepare(dict(root=str(self.root),directory=str(folder),config=config))['manifest']
        self.assertEqual(manifest['stages'][0]['program'],'neb')
        text=(folder/'neb/neb.in').read_text()
        self.assertIn('BEGIN_PATH_INPUT',text)
        self.assertEqual(text.count('ATOMIC_POSITIONS angstrom'),3)
        self.assertEqual(len(read(folder/'neb/input-images.extxyz',index=':')),3)

    def test_periodic_gas_reference_uses_molecular_thermochemistry(self):
        folder=self.root/'gas'; (folder/'hydrogen').mkdir(parents=True)
        write(folder/'hydrogen/input.extxyz',Atoms('H',positions=[[1,1,1]],cell=[6,6,6],pbc=True))
        displacements=[]
        for axis in range(3):
            for sign in [-1,1]:
                stage='force-'+str(axis)+'-'+str(sign)
                (folder/stage).mkdir()
                shutil.copyfile(ROOT/'tests/fixtures/qe-hydrogen-atom-scf.out',folder/stage/'qe.out')
                displacements.append(dict(stage=stage,atom=0,axis=axis,sign=sign))
        plan=dict(indices=[0],displacements=displacements,delta_A=.01,options=dict(model='ideal-gas',geometry='monatomic',symmetrynumber=1,spin=.5))
        manifest=dict(config=dict(models=[dict(id='hydrogen')],thermochemistry=dict(temperature_K=298.15,pressure_Pa=100000)),analysis=dict(vibrations={'hydrogen':plan}))
        correction,records=thermal_corrections(folder,manifest,{})
        self.assertTrue(-.5 < correction['hydrogen'] < -.05)
        self.assertEqual(records['hydrogen']['method'],'ideal-gas')

    def test_generated_batch_script_runs_and_reports_failed_stages(self):
        bash = Path(shutil.which('git')).resolve().parents[1] / 'bin/bash.exe' if sys.platform == 'win32' else Path(shutil.which('bash'))
        if not bash.is_file():
            self.skipTest('Bash is unavailable')
        folder = self.root / 'stage'
        folder.mkdir()
        (folder / 'qe.in').write_text('input')
        manifest = dict(programs={'pw': str(bash).replace('\\', '/')}, stages=[dict(id='stage', program='pw', folder='stage', input='qe.in', output='qe.out', calculation='scf', arguments=['-c', "printf 'convergence has been achieved\\nJOB DONE.\\n'"])])
        script = self.root / 'workflow.sh'
        script.write_text(build_runner(manifest), newline='\n')
        done = subprocess.run([str(bash), str(script)], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads((self.root / 'workflow-status.json').read_text())['status'], 'completed')
        manifest['stages'][0]['arguments'] = ['-c', 'exit 5']
        script.write_text(build_runner(manifest), newline='\n')
        done = subprocess.run([str(bash), str(script)], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(done.returncode, 5)
        self.assertEqual(json.loads((self.root / 'workflow-status.json').read_text())['stages'][0]['status'], 'failed')
        manifest=dict(programs={'bader':str(bash).replace('\\','/')},stages=[dict(id='bader',program='bader',folder='empty-stage',output='post.out',arguments=['-c','printf partition > ACF.dat'],outputs=['ACF.dat'])])
        script.write_text(build_runner(manifest),newline='\n')
        done=subprocess.run([str(bash),str(script)],cwd=self.root,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertEqual((self.root/'empty-stage/ACF.dat').read_text(),'partition')


if __name__ == '__main__':
    unittest.main()
