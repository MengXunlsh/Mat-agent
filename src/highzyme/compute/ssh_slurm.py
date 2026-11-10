"""Native OpenSSH transport and Slurm jobs; no remote daemon or package install."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid

from highzyme.compute.connector import child_path


def validate_profile(value):
    profile = {key: value.get(key, "") for key in ("host", "user", "identity_file", "remote_root", "partition",
               "account", "qos", "setup_script", "qe_command", "python_command", "mpi_command")}
    profile["port"] = None if value.get("port") in (None, "") else int(value["port"])
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]*", profile["host"]):
        raise ValueError("Enter a hostname or existing SSH alias")
    if profile["user"] and not re.fullmatch(r"[a-zA-Z0-9_.-]+", profile["user"]):
        raise ValueError("Invalid SSH username")
    if profile["port"] is not None and not 1 <= profile["port"] <= 65535:
        raise ValueError("SSH port must be 1–65535")
    if profile["identity_file"] and not Path(profile["identity_file"]).expanduser().is_file():
        raise ValueError("The selected SSH key file does not exist")
    if profile["remote_root"] and not profile["remote_root"].startswith(("/", "~/")):
        raise ValueError("Remote directory must be absolute or start with ~/")
    for key in ("partition", "account", "qos"):
        if profile[key] and not re.fullmatch(r"[a-zA-Z0-9_.-]+", profile[key]):
            raise ValueError("Invalid " + key)
    commands = value.get("program_commands", {})
    if isinstance(commands, dict):
        commands = {key: command for key, command in commands.items() if command not in ('', None)}
    if not isinstance(commands, dict) or any(key not in ("dos", "projwfc", "bands", "pp", "neb", "bader") or not isinstance(command, str) or not command.strip() for key, command in commands.items()):
        raise ValueError("Invalid compute program commands")
    profile["program_commands"] = commands
    return profile


def ssh_args(profile):
    args = [shutil.which("ssh") or "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            "-o", "StrictHostKeyChecking=yes", "-o", "ServerAliveInterval=15"]
    # An alias retains its own configured port and identity unless explicitly overridden.
    if profile["port"] is not None:
        args += ["-p", str(profile["port"])]
    if profile["user"]:
        args += ["-l", profile["user"]]
    if profile["identity_file"]:
        args += ["-i", str(Path(profile["identity_file"]).expanduser()), "-o", "IdentitiesOnly=yes"]
    return args + [profile["host"]]


def checked_run(args, **kwargs):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, **kwargs)
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        if not message:
            output = result.stdout.decode("utf-8", errors="replace").strip()
            try:
                message = json.loads(output).get("error", output)
            except ValueError:
                message = output
        if "Host key verification failed" in message:
            message = "SSH host is not trusted yet. Verify its fingerprint and connect once using your SSH client."
        elif "Permission denied" in message:
            message = "SSH authentication failed. Check the username, selected key and its file permissions. " + message
        raise ValueError(message or "SSH operation failed")
    return result.stdout


def remote(profile, request):
    payload = base64.b64encode(json.dumps({**request, "profile": profile}).encode()).decode()
    worker = Path(__file__).with_name("remote_worker.py").read_bytes()
    output = checked_run(ssh_args(profile) + ["python3 - " + shlex.quote(payload)], input=worker)
    result = json.loads(output)
    if "error" in result:
        raise ValueError(result["error"])
    return result["result"]


class SSHSlurm:
    def __init__(self, profile, state):
        self.profile = validate_profile(profile)
        self.state = Path(state)

    def probe(self):
        args = ssh_args(self.profile)
        config = checked_run([args[0], "-G", *args[1:]]).decode("utf-8", errors="replace")
        connection = dict(line.split(" ", 1) for line in config.splitlines()
                          if line.split(" ", 1)[0] in ("hostname", "port", "user"))
        result = remote(self.profile, {"action": "probe"})
        result["connection"] = connection
        return result

    def record(self, job_id):
        if not re.fullmatch(r"job-[a-f0-9]{32}", job_id):
            raise ValueError("Invalid job ID")
        return json.loads((self.state / job_id / "job.json").read_text(encoding="utf-8"))

    def submit(self, value):
        job_id = value.get("job_id") or "job-" + uuid.uuid4().hex
        if not re.fullmatch(r"job-[a-f0-9]{32}", job_id):
            raise ValueError("Invalid job ID")
        if (self.state / job_id / "job.json").exists():
            return self.record(job_id)
        script = value.get("script", "")
        if not isinstance(script, str) or not script.strip() or len(script) > 1_000_000:
            raise ValueError("Provide a non-empty script of at most 1 MB")
        task = {"capability": value.get("capability", "shell"), "script": script,
                "timeout_seconds": int(value.get("timeout_seconds", 300)),
                "memory_mb": int(value.get("memory_mb", 1024)),
                "ranks": int(value.get("ranks", 1)), "threads": int(value.get("threads", value.get("cores", 1)))}
        if value.get("launch_mode") == "workflow":
            task["launch_mode"] = "workflow"
        for key, limit in (("ranks", 65536), ("threads", 1024), ("memory_mb", 2**31), ("timeout_seconds", 30 * 86400)):
            if not 1 <= task[key] <= limit:
                raise ValueError("Invalid resource request: " + key)
        inputs = []
        for row in value.get("input_files", []):
            source = Path(row["source"])
            target = row.get("target") or source.name
            child_path(Path.cwd(), target)
            if not source.is_file():
                raise ValueError("Input file not found: " + str(source))
            inputs.append((source, target))
        for name in value.get("files", {}):
            child_path(Path.cwd(), name)
        health = remote(self.profile, {"action": "probe", "detailed": False})
        if not health["ready"] or task["capability"] not in health["capabilities"]:
            raise ValueError("The resource is not ready for " + task["capability"])
        missing = [name for name in value.get('required_programs', []) if not health['programs'].get('quantum_espresso' if name == 'pw' else name)]
        if missing:
            raise ValueError('Configure these programs before submitting: ' + ', '.join(missing))
        folder = health["remote_root"].rstrip("/") + "/" + job_id
        local = self.state / job_id
        local.mkdir(parents=True, exist_ok=True)
        sources = []
        for source, target in inputs:
            with source.open("rb") as stream:
                sources.append({"file": target, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()})
        with tempfile.TemporaryDirectory(prefix="highzyme-stage-") as temporary:
            archive = Path(temporary) / "inputs.tar"
            with tarfile.open(archive, "w") as bundle:
                for source, target in inputs:
                    bundle.add(source, arcname=target, recursive=False)
                for name, text in value.get("files", {}).items():
                    item = Path(temporary) / name
                    item.parent.mkdir(parents=True, exist_ok=True)
                    item.write_text(text, encoding="utf-8")
                    bundle.add(item, arcname=name, recursive=False)
                worker = Path(__file__).with_name('remote_worker.py').read_bytes()
                entry = tarfile.TarInfo('highzyme-worker.py')
                entry.size = len(worker)
                bundle.addfile(entry, io.BytesIO(worker))
            request = {"action": "submit", "id": job_id, "folder": folder, "task": task, "profile": self.profile}
            payload = base64.b64encode(json.dumps(request).encode()).decode()
            command = 'mkdir -p ' + shlex.quote(folder) + ' && tar -xf - -C ' + shlex.quote(folder)
            command += ' && python3 ' + shlex.quote(folder + '/highzyme-worker.py') + ' ' + shlex.quote(payload)
            # Transfer and submit in one connection; a lost reply still retains this attempt.
            record = {"id": job_id, "remote_directory": folder, "status": "submitting", "sources": sources, 'resources': {key: task[key] for key in ('ranks','threads','memory_mb','timeout_seconds')}}
            (local / "job.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            try:
                with archive.open('rb') as stream:
                    response = json.loads(checked_run(ssh_args(self.profile) + [command], stdin=stream))
                if 'error' in response:
                    record.update(status='failed', error=response['error'])
                else:
                    record.update(response['result'])
            except Exception as error:
                record.update(status="submission_unknown", error=str(error))
            finally:
                (local / "job.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record

    def update(self, job_id, action):
        row = self.record(job_id)
        fallback = {key: row[key] for key in ('id', 'status', 'resources', 'remote_directory') if key in row}
        result = remote(self.profile, {"action": action, "folder": row["remote_directory"], "record": fallback})
        row.update(result)
        (self.state / job_id / "job.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
        return row

    def download(self, job_id, name, destination):
        row = self.record(job_id)
        child_path(Path.cwd(), name)
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        source = str(PurePosixPath(row["remote_directory"]) / name)
        with target.open("wb") as stream:
            process = subprocess.run(ssh_args(self.profile) + ["cat -- " + shlex.quote(source)], stdout=stream,
                                     stderr=subprocess.PIPE, timeout=300,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if process.returncode:
            target.unlink(missing_ok=True)
            raise ValueError(process.stderr.decode("utf-8", errors="replace").strip())
        with target.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        return {"file": str(target), "bytes": target.stat().st_size, "sha256": digest}

    def download_many(self, job_id, names, destination):
        row = self.record(job_id)
        target = Path(destination)
        for name in names:
            child_path(target, name)
        command = 'tar -cf - -C ' + shlex.quote(row['remote_directory']) + ' -- ' + ' '.join(shlex.quote(name) for name in names)
        with tempfile.TemporaryFile() as stream:
            done = subprocess.run(ssh_args(self.profile) + [command], stdout=stream, stderr=subprocess.PIPE, timeout=300,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if done.returncode:
                raise ValueError(done.stderr.decode('utf-8', errors='replace').strip())
            stream.seek(0)
            with tarfile.open(fileobj=stream) as archive:
                for member in archive.getmembers():
                    if member.name not in names or not member.isfile():
                        raise ValueError('Unexpected file in compute result archive')
                archive.extractall(target, filter='data')
        return {'files': names}


def dispatch(request):
    if request["action"] == "validate":
        return validate_profile(request["profile"])
    if request["action"] == "choose_key":
        from highzyme.infrastructure.file_dialogs import choose_file
        return choose_file('key')
    backend = SSHSlurm(request["profile"], request["state"])
    action = request["action"]
    if action == "probe":
        return backend.probe()
    if action == "submit":
        return backend.submit(request["task"])
    if action in ("status", "cancel"):
        return backend.update(request["job_id"], action)
    if action == "download":
        return backend.download(request["job_id"], request["file"], request["destination"])
    if action == "download_many":
        return backend.download_many(request['job_id'], request['files'], request['destination'])
    raise ValueError("Unknown compute operation")


if __name__ == "__main__":
    try:
        print(json.dumps({"result": dispatch(json.load(sys.stdin))}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
