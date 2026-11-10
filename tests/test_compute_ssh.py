import ast
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import io
import tarfile
from types import SimpleNamespace
from unittest.mock import patch

from highzyme.compute import remote_worker
from highzyme.compute.qe_calculation import collect, prepare
from highzyme.compute.ssh_slurm import SSHSlurm, ssh_args, validate_profile


ROOT = Path(__file__).resolve().parents[1]


class ComputeSSHTests(unittest.TestCase):
    def test_profiles_reuse_openssh_without_reading_private_key(self):
        profile = validate_profile({"host": "my-cluster"})
        args = ssh_args(profile)
        self.assertEqual(args[-1], "my-cluster")
        self.assertNotIn("-p", args)
        self.assertIn("BatchMode=yes", args)
        for invalid in ({"host": "-oProxyCommand=bad"}, {"host": "cluster", "port": 0},
                        {"host": "cluster", "remote_root": "relative/path"},
                        {"host": "cluster", "identity_file": "missing-private-key.pem"}):
            with self.assertRaises(ValueError):
                validate_profile(invalid)
        ast.parse((ROOT / "src/highzyme/compute/remote_worker.py").read_text(), feature_version=(3, 6))

    def test_slurm_accounting_failure_timeout_and_cancel_states(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for state, code, expected in (("FAILED", "1:0", "failed"), ("TIMEOUT", "0:15", "timed_out"),
                                          ("CANCELLED by 1", "0:15", "cancelled"), ("COMPLETED", "1:0", "failed")):
                (folder / "job.json").write_text(json.dumps({"id": "test", "scheduler_id": "123", "status": "queued"}))
                with self.subTest(state=state), patch.object(remote_worker, "run", side_effect=[
                        (0, "", ""), (0, "123|" + state + "|" + code + "|", "")]):
                    result = remote_worker.status({"folder": temporary, "action": "status"})
                    self.assertEqual(result["status"], expected)
                    self.assertEqual(result["exit_code"], code)

    def test_prepare_real_ase_input_and_reject_mismatched_pseudopotential(self):
        from ase.io import read

        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            pseudo = folder / "si.upf"
            pseudo.write_text('<UPF><PP_HEADER element="Si" /></UPF>')
            request = {"structure_file": str(ROOT / "examples/general-research/qe-smoke/silicon.extxyz"),
                       "directory": str(folder / "calculation"), "pseudopotentials": {"Si": str(pseudo)},
                       "parameters": json.loads((ROOT / "examples/general-research/qe-smoke/parameters.json").read_text())}
            result = prepare(request)
            atoms = read(folder / "calculation/qe.in", format="espresso-in")
            self.assertEqual(atoms.get_chemical_formula(), "Si2")
            self.assertGreater(atoms.cell.volume, 0)
            self.assertEqual(result["input_files"][0]["target"], "pseudo/si.upf")
            pseudo.write_text('<UPF><PP_HEADER element="H" /></UPF>')
            with self.assertRaisesRegex(ValueError, "element mismatch"):
                prepare(request)

    def test_known_submission_is_returned_without_network_or_another_scheduler_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            job_id = 'job-' + 'a' * 32
            folder = Path(temporary) / job_id
            folder.mkdir()
            record = {"id": job_id, "status": "submission_unknown", "remote_directory": "/jobs/" + job_id}
            (folder / 'job.json').write_text(json.dumps(record))
            backend = SSHSlurm({"host": "example-cluster"}, temporary)
            self.assertEqual(backend.submit({"job_id": job_id}), record)

    def test_queue_reason_and_elapsed_are_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "job.json").write_text(json.dumps({"id": "test", "scheduler_id": "123", "status": "queued"}))
            with patch.object(remote_worker, "run", return_value=(0, "PENDING|Resources|0:00", "")):
                result = remote_worker.status({"folder": temporary, "action": "status"})
            self.assertEqual(result["reason"], "Resources")
            self.assertEqual(result["elapsed"], "0:00")
            with patch.object(remote_worker, "run", side_effect=[(0, "", ""), (0, "123|TIMEOUT|0:15|00:05:00|TimeLimit|", "")]):
                result = remote_worker.status({"folder": temporary, "action": "status"})
            self.assertEqual(result["status"], "timed_out")
            self.assertEqual(result["elapsed"], "00:05:00")
            self.assertEqual(result["reason"], "TimeLimit")

    def test_interrupted_submission_is_checked_without_replaying(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            record=dict(id='job-'+'b'*32, status='submission_unknown')
            request=dict(action='status', folder=temporary, record=record)
            self.assertEqual(remote_worker.status(request)['status'], 'failed')
            (folder/'submit.sh').write_text('prepared scheduler script')
            record['status']='submission_unknown'
            with patch.object(remote_worker,'run',return_value=(0,'','')) as external:
                self.assertEqual(remote_worker.status(request)['status'],'submission_unknown')
                self.assertEqual(external.call_args.args[0][0],'sacct')

    def test_selected_outputs_are_downloaded_in_one_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); job_id='job-'+'c'*32
            state=root/job_id; state.mkdir()
            (state/'job.json').write_text(json.dumps(dict(remote_directory='/jobs/'+job_id)))
            def transfer(_args,stdout,**_kwargs):
                with tarfile.open(fileobj=stdout,mode='w') as archive:
                    data=b'QE output'
                    member=tarfile.TarInfo('stage/qe.out'); member.size=len(data)
                    archive.addfile(member,io.BytesIO(data))
                return SimpleNamespace(returncode=0,stderr=b'')
            backend=SSHSlurm(dict(host='example-cluster'),root)
            with patch('highzyme.compute.ssh_slurm.subprocess.run',side_effect=transfer) as external:
                backend.download_many(job_id,['stage/qe.out'],root/'outputs')
                self.assertEqual(external.call_count,1)
            self.assertEqual((root/'outputs/stage/qe.out').read_bytes(),b'QE output')

    def test_transfer_and_submit_share_a_connection_after_one_environment_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); source=root/'qe.in'; source.write_text('prepared input')
            backend=SSHSlurm(dict(host='example-cluster'),root/'state')
            def submit(_args,stdin):
                with tarfile.open(fileobj=stdin) as archive:
                    self.assertEqual(set(archive.getnames()), {'qe.in','highzyme-worker.py'})
                    self.assertEqual(archive.extractfile('qe.in').read(),b'prepared input')
                return json.dumps({'result':dict(status='queued',scheduler_id='123')}).encode()
            with patch('highzyme.compute.ssh_slurm.remote',return_value=dict(ready=True,capabilities=['quantum_espresso'],programs={'quantum_espresso':'pw.x'},remote_root='/jobs')) as probe:
                with patch('highzyme.compute.ssh_slurm.checked_run',side_effect=submit) as transfer:
                    result=backend.submit(dict(job_id='job-'+'d'*32,script='pw.x -in qe.in',capability='quantum_espresso',input_files=[dict(source=str(source),target='qe.in')]))
            self.assertEqual(result['scheduler_id'],'123')
            self.assertEqual(probe.call_count,1); self.assertEqual(transfer.call_count,1)

    def test_collect_real_qe7_output_and_distinguish_geometry_and_exit_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "pseudo").mkdir()
            (folder / "pseudo/si.upf").write_text("parser fixture")
            record = {"parameters": {"calculation": "scf"}, "pseudopotentials": [{"element": "Si", "file": "si.upf"}],
                      "structure": {"formula": "Si2"}}
            (folder / "request.json").write_text(json.dumps(record))
            shutil.copyfile(ROOT / "tests/fixtures/qe-silicon-scf.out", folder / "qe.out")
            request = {"directory": temporary, "job": {"status": "completed", "scheduler_id": "123", "exit_code": "0:0"}}
            result = collect(request)
            self.assertEqual(result["result"]["status"], "converged")
            self.assertAlmostEqual(result["result"]["energy_Ry"], -14.50260042)
            self.assertTrue((folder / "final.cif").exists())
            self.assertNotIn("result.json", result["result"]["sources"])
            self.assertEqual(collect(request)["result"], result["result"])
            request["job"]["status"] = "failed"
            self.assertIsNone(collect(request)["result"]["energy_Ry"])
            request["job"]["status"] = "completed"
            record["parameters"]["calculation"] = "relax"
            (folder / "request.json").write_text(json.dumps(record))
            self.assertEqual(collect(request)["result"]["status"], "not_converged")


if __name__ == "__main__":
    unittest.main()
