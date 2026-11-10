"""One local CPU job at a time. No shell commands, model API, cloud or automatic failed-job replay."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from highzyme.compute.dft_jobs import DFTJobStore,clean_environment
from highzyme.infrastructure.executor_lease import ExecutorLease

def supervise(root,idle_seconds=60):
    store=DFTJobStore(root)
    try:lease=ExecutorLease(store.root/'supervisor')
    except RuntimeError:return
    try:
        # A lost worker is recorded, never re-run behind the user's back.
        for row in store.rows('running'):
            folder=store.folder(row['job_id'])
            if (folder/'result.json').is_file():
                data=json.loads((folder/'result.json').read_text('utf8'))
                if data.get('request_sha256')==row['request_hash']:
                    store.update(row['job_id'],status='succeeded',result_sha256=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest());continue
            store.update(row['job_id'],status='interrupted',error='Previous supervisor ended before reconciliation; review saved files, do not automatically resubmit.')
        idle=time.monotonic()
        while True:
            queued=store.rows('queued')
            if not queued:
                if time.monotonic()-idle>=idle_seconds:
                    with store.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        if db.execute("SELECT count(*) FROM jobs WHERE status='queued'").fetchone()[0]==0:
                            # Release the lease before submitters can commit and ensure a new worker.
                            lease.close();return
                time.sleep(.25);continue
            idle=time.monotonic();row=queued[0];ident=row['job_id'];folder=store.folder(ident)
            if store.get(ident)['status']!='queued':continue
            config=json.loads(row['config_json']);python=Path(config['python'])
            if hashlib.sha256((folder/'request.json').read_bytes()).hexdigest()!=row['request_hash']:
                store.update(ident,status='failed',error='Input hash changed before execution');continue
            worker='qe_worker.py' if config.get('backend')=='qe' else 'psi4_worker.py'
            args=[str(python),'-B','-X','utf8',str(Path(__file__).with_name(worker)),
                '--job',str(folder),'--threads',str(config['threads']),'--memory-mb',str(config['memory_mb'])]
            try:
                with (folder/'stdout.log').open('ab') as out:
                    process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,
                        env=clean_environment(python),creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,close_fds=True,
                        start_new_session=(os.name!='nt' and config.get('backend')=='qe'))
                    from highzyme.compute.process_tree import ComputeProcessTree
                    tree=ComputeProcessTree(process,config['memory_mb']) if config.get('backend')=='qe' else None
                    store.update(ident,status='running',pid=process.pid);start=time.monotonic();outcome=None
                    while process.poll() is None:
                        if store.get(ident)['cancel_requested']:outcome='cancelled'
                        elif time.monotonic()-start>config['timeout_seconds']:outcome='timed_out'
                        elif config.get('backend')=='qe' and (folder/'qe.out').is_file():
                            import re
                            text=(folder/'qe.out').read_text('utf8',errors='replace')[-16000:]
                            estimate=re.search(r'Estimated max dynamical RAM per process\s*>\s*([\d.]+)\s*(GB|MB)',text)
                            if estimate and float(estimate[1])*(1024 if estimate[2]=='GB' else 1)>config['memory_mb']:
                                outcome='resource_limited'
                        if outcome:
                            if tree:tree.close()
                            else:process.kill()
                            process.wait();break
                        time.sleep(.25)
                    if tree:tree.close()
                if outcome:store.update(ident,status='failed' if outcome=='resource_limited' else outcome,error='QE memory estimate exceeds configured local budget; no result accepted.' if outcome=='resource_limited' else 'Local job cancelled' if outcome=='cancelled' else 'Configured wall-time limit reached')
                elif process.returncode!=0 or not (folder/'result.json').is_file():
                    log=(folder/'stdout.log').read_text('utf8',errors='replace')[-16000:]
                    reason=('Electronic SCF did not converge; no numerical result accepted.' if 'SCFConvergenceError' in log else
                        'Geometry optimization did not converge; no optimized result accepted.' if 'OptimizationConvergenceError' in log else
                        'DFT backend did not finish successfully; inspect retained psi4.out/stdout.log')
                    store.update(ident,status='failed',error=reason)
                else:
                    result=json.loads((folder/'result.json').read_text('utf8'))
                    if result.get('request_sha256')!=row['request_hash']:raise ValueError('Output input-hash mismatch')
                    store.update(ident,status='succeeded',result_sha256=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest())
            except Exception as exc:store.update(ident,status='failed',error=type(exc).__name__+': local compute launch or result reconciliation failed')
            idle=time.monotonic()
    finally:lease.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work-dir',required=True);args=p.parse_args();supervise(args.work_dir)
