"""Durable case-scoped local DFT jobs; web requests never wait for electronic structure."""
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,os,re,sqlite3,subprocess,sys,time,uuid
from contextlib import closing
from highzyme.compute.dft_schema import validate_task
from highzyme.infrastructure.executor_lease import ExecutorLease
from highzyme.infrastructure.runtime_paths import PROJECT_ROOT

TERMINAL={'succeeded','failed','cancelled','timed_out','interrupted'}
JOB=re.compile(r'DFT_[a-f0-9]{32}\Z')

def clean_environment(python):
    """Compute subprocesses receive no application/model credentials."""
    keys={'SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','PROGRAMDATA','LANG','LC_ALL'}
    env={k:v for k,v in os.environ.items() if k.upper() in keys}
    prefix=Path(python).parent
    paths=[prefix,prefix/'Library/bin',prefix/'Scripts',Path(os.environ.get('SYSTEMROOT','/'))/'System32'] if os.name=='nt' else [prefix,Path('/usr/bin'),Path('/bin')]
    env['PATH']=os.pathsep.join(map(str,paths))
    env.update(OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',PYTHONUTF8='1',PYTHONNOUSERSITE='1')
    return env

@dataclass(frozen=True)
class LocalDFTConfig:
    work_dir: Path
    python: Path
    threads: int=2
    memory_mb: int=2048
    timeout_seconds: int=600

    def __post_init__(self):
        for key in ('work_dir','python'):object.__setattr__(self,key,Path(getattr(self,key)).resolve())
        if not 1<=self.threads<=4 or not 512<=self.memory_mb<=4096 or not 1<=self.timeout_seconds<=3600:
            raise ValueError('DFT resources exceed the local integration bounds')

    @classmethod
    def configured(cls):
        default=PROJECT_ROOT/'.tools/dft/psi4'/('python.exe' if os.name=='nt' else 'bin/python')
        from highzyme.infrastructure.access_context import ACTOR
        actor=ACTOR.get() or {}
        work=Path(actor['browser_root'])/'dft_jobs' if actor.get('browser_root') else Path(os.environ.get('HIGHZYME_DFT_WORK_DIR',PROJECT_ROOT/'runtime/dft_jobs'))
        return cls(work,
            Path(os.environ.get('HIGHZYME_DFT_PYTHON',default)),
            int(os.environ.get('HIGHZYME_DFT_THREADS','2')),int(os.environ.get('HIGHZYME_DFT_MEMORY_MB','2048')),
            int(os.environ.get('HIGHZYME_DFT_TIMEOUT_SECONDS','600')))

    def public(self):
        return {'backend':'psi4','available':self.python.is_file(),'system':'local','paid_compute':False,
            'supported_system':'finite_molecule_or_cluster','periodic_supported':False,
            'threads':self.threads,'memory_mb':self.memory_mb,'timeout_seconds':self.timeout_seconds,
            'max_atoms':32,'max_concurrent_jobs':1,
            'visualization_properties':['electron_density','spin_density','frontier_orbitals'],
            'deployment_interface':'Configure HIGHZYME_DFT_PYTHON and HIGHZYME_DFT_WORK_DIR; inputs/results are versioned JSON and XYZ.'}

class DFTJobStore:
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True);self.database=self.root/'jobs.sqlite3'
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS jobs(
              job_id TEXT PRIMARY KEY,owner TEXT NOT NULL,request_hash TEXT NOT NULL,
              status TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,
              cancel_requested INTEGER NOT NULL DEFAULT 0,pid INTEGER,error TEXT,
              config_json TEXT NOT NULL,UNIQUE(owner,request_hash));
              CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status,created);''')
            if 'result_sha256' not in {r[1] for r in db.execute('PRAGMA table_info(jobs)')}:
                db.execute('ALTER TABLE jobs ADD COLUMN result_sha256 TEXT')

    def connect(self):
        connection=sqlite3.connect(self.database,timeout=30);connection.row_factory=sqlite3.Row
        return closing_transaction(connection)

    def folder(self,job_id):
        if not isinstance(job_id,str) or not JOB.fullmatch(job_id):raise ValueError('Invalid DFT job identifier')
        return self.root/job_id

    def get(self,job_id,owner=None):
        self.folder(job_id)
        with self.connect() as db:
            row=db.execute('SELECT * FROM jobs WHERE job_id=?'+(' AND owner=?' if owner is not None else ''),
                (job_id,owner) if owner is not None else (job_id,)).fetchone()
        if row is None:raise ValueError('DFT job is unavailable in this case')
        return dict(row)

    def submit(self,owner,task,config):
        validate_task(task);raw=json.dumps(task,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
        digest=hashlib.sha256(raw).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT * FROM jobs WHERE owner=? AND request_hash=?',(owner,digest)).fetchone()
            if existing:return dict(existing),False
            if db.execute("SELECT count(*) FROM jobs WHERE status NOT IN ('succeeded','failed','cancelled','timed_out','interrupted')").fetchone()[0]>=16:
                raise ValueError('Local DFT queue is full')
            ident='DFT_'+uuid.uuid4().hex;folder=self.folder(ident);folder.mkdir()
            (folder/'request.json').write_bytes(raw)
            config_data={'python':str(config.python),'threads':config.threads,'memory_mb':config.memory_mb,'timeout_seconds':config.timeout_seconds}
            if getattr(config,'backend',None)=='qe':
                config_data.update(backend='qe',executable=str(config.executable),pseudo_dir=str(config.pseudo_dir))
                (folder/'backend.json').write_text(json.dumps(config_data),encoding='utf8')
            now=time.time();db.execute('INSERT INTO jobs(job_id,owner,request_hash,status,created,updated,config_json) VALUES(?,?,?,?,?,?,?)',
                (ident,owner,digest,'queued',now,now,json.dumps(config_data)))
        return self.get(ident,owner),True

    def update(self,job_id,**values):
        if not values or set(values)-{'status','pid','error','cancel_requested','result_sha256'}:raise ValueError('Unsupported DFT state update')
        with self.connect() as db:
            db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+',updated=? WHERE job_id=?',
                [*values.values(),time.time(),job_id])

    def cancel(self,job_id,owner):
        row=self.get(job_id,owner)
        if row['status'] not in TERMINAL:
            self.update(job_id,cancel_requested=1,**({'status':'cancelled'} if row['status']=='queued' else {}))
        return self.get(job_id,owner)

    def rows(self,status):
        with self.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM jobs WHERE status=? ORDER BY created',(status,))]

    def public(self,row,include_result=False):
        folder=self.folder(row['job_id']);raw=(folder/'request.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['request_hash']:raise ValueError('Saved DFT inputs changed; review required')
        task=json.loads(raw)
        data={k:row[k] for k in ('job_id','status','created','updated','error')}
        data.update(label=task['label'],method=task['method'],basis=task.get('basis','plane waves / PAW'),calculation=task['calculation'],
            structure_source=task['structure']['source'],request_sha256=row['request_hash'],backend=task.get('backend','psi4'))
        if include_result and row['status']=='succeeded':
            result_raw=(folder/'result.json').read_bytes();digest=hashlib.sha256(result_raw).hexdigest()
            if row.get('result_sha256') and digest!=row['result_sha256']:raise ValueError('Saved DFT result hash changed; review required')
            if not row.get('result_sha256'):self.update(row['job_id'],result_sha256=digest)
            result=json.loads(result_raw)
            if result.get('request_sha256')!=row['request_hash']:raise ValueError('DFT output does not match its input')
            data['calculation_result']=result
            data['result_sha256']=digest
        from highzyme.compute.dft_visualization import BASE_ARTIFACTS,registered_names
        names=BASE_ARTIFACTS|{'backend.json'}|registered_names(folder)
        data['artifacts']=[{'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(folder.iterdir()) if p.is_file() and p.name in names]
        return data

class closing_transaction:
    def __init__(self,db):self.db=db
    def __enter__(self):return self.db
    def __exit__(self,kind,value,tb):
        try:self.db.rollback() if kind else self.db.commit()
        finally:self.db.close()

def ensure_supervisor(store):
    """Detached worker survives a web-service restart; the lease serializes all cases."""
    try:lease=ExecutorLease(store.root/'supervisor')
    except RuntimeError:return
    lease.close()
    args=[sys.executable,'-B','-X','utf8',str(Path(__file__).with_name('dft_supervisor.py')),'--work-dir',str(store.root)]
    flags=(subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP) if os.name=='nt' else 0
    with (store.root/'supervisor.log').open('ab') as out:
        subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,
            env=clean_environment(sys.executable),creationflags=flags,start_new_session=os.name!='nt',close_fds=True)

def case_owner(context):
    if not isinstance(context,dict) or not isinstance(context.get('case_id'),str) or not context.get('case_scope'):
        raise ValueError('DFT jobs require a server-bound case and storage scope')
    # A logical namespace remains stable when the project moves from Windows to Linux.
    namespace=os.environ.get('HIGHZYME_DFT_NAMESPACE','highzyme')
    if not namespace.strip() or len(namespace)>200:raise ValueError('Invalid DFT workspace namespace')
    return hashlib.sha256((namespace+'\0'+context['case_id']).encode()).hexdigest()
