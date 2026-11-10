"""User-operated compute endpoint, independent of the mat-agent website."""
from __future__ import annotations

import argparse
import base64
import hmac
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs


def child_path(root: Path, name: str) -> Path:
    if not name or "\\" in name or ":" in name or any(p in ("", ".", "..") for p in name.split("/")):
        raise ValueError("Invalid relative file path")
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("File must stay inside the job directory")
    return target


class ComputeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, root: Path, token: str, scheduler="local", partition=""):
        if len(token) < 24:
            raise ValueError("Use a token of at least 24 characters")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.token, self.scheduler, self.partition = token, scheduler, partition
        self.jobs, self.lock = {}, threading.RLock()
        if scheduler == "slurm" and not all(shutil.which(x) for x in ("sbatch", "squeue", "scancel")):
            raise ValueError("Slurm requires sbatch, squeue and scancel on the execution host")
        for file in self.root.glob("*/job.json"):
            row = json.loads(file.read_text(encoding="utf-8"))
            if row["status"] in ("queued", "running") and row.get("scheduler") != "slurm":
                row["status"] = "interrupted"
                file.write_text(json.dumps(row), encoding="utf-8")
            self.jobs[row["id"]] = row
        super().__init__(address, Handler)

    def health(self):
        capabilities = ["python", "shell"]
        programs = {name: shutil.which(binary) for name, binary in (("quantum_espresso", "pw.x"), ("psi4", "psi4"), ("cp2k", "cp2k.psmp"), ("lammps", "lmp"))}
        if importlib.util.find_spec("psi4"):
            programs["psi4"] = "python:psi4"
        capabilities += [key for key, value in programs.items() if value]
        return {"protocol": "highzyme-compute-v1", "capabilities": capabilities, "programs": {k: bool(v) for k, v in programs.items()}, "scheduler": self.scheduler, "platform": sys.platform, "cpu_count": os.cpu_count()}

    def persist(self, row):
        clean = {k: v for k, v in row.items() if k != "process"}
        (self.root / row["id"] / "job.json").write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")

    def submit(self, value):
        capability = value.get("capability", "python")
        if capability not in self.health()["capabilities"]:
            raise ValueError("Required capability is unavailable")
        script = value.get("script", "")
        if not isinstance(script, str) or not script.strip() or len(script) > 1_000_000:
            raise ValueError("Provide a non-empty script of at most 1 MB")
        timeout = int(value.get("timeout_seconds", 300))
        if not 1 <= timeout <= 86400:
            raise ValueError("Timeout must be 1–86400 seconds")
        cores = int(value.get("cores", 1))
        if not 1 <= cores <= 64:
            raise ValueError("Cores must be 1–64")
        if self.scheduler == "local" and cores > (os.cpu_count() or 1):
            raise ValueError("Requested cores exceed this execution host")
        job_id = "job_" + uuid.uuid4().hex
        folder = self.root / job_id
        folder.mkdir()
        for name, text in value.get("files", {}).items():
            target = child_path(folder, name)
            if not isinstance(text, str):
                raise ValueError("Input files must contain text")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        is_python = capability == "python" or (capability == "psi4" and not shutil.which("psi4"))
        entry = folder / ("task.py" if is_python else "task.sh" if os.name != "nt" else "task.ps1")
        entry.write_text(script, encoding="utf-8")
        command = [sys.executable, str(entry)] if is_python else (["pwsh", "-NoProfile", "-File", str(entry)] if os.name == "nt" else ["bash", str(entry)])
        row = {"id": job_id, "capability": capability, "scheduler": self.scheduler, "status": "queued", "created_at": time.time(), "timeout_seconds": timeout, "cores": cores}
        with self.lock:
            self.jobs[job_id] = row
            self.persist(row)
        if self.scheduler == "slurm":
            import shlex
            wrapper = folder / "submit.sh"
            wrapper.write_text("#!/bin/bash\ncd " + shlex.quote(str(folder)) + "\n" + shlex.join(command) + '\ncode=$?\nprintf "%s" "$code" > .exit-code\nexit "$code"\n', encoding="utf-8")
            args = ["sbatch", "--parsable", "--cpus-per-task", str(cores), "--time", str(max(1, (timeout + 59) // 60)), "--output", str(folder / "stdout.log"), "--error", str(folder / "stderr.log")]
            if self.partition:
                args.extend(["--partition", self.partition])
            done = subprocess.run(args + [str(wrapper)], capture_output=True, text=True, timeout=30, check=True)
            scheduler_id = done.stdout.strip().split(";")[0]
            if not scheduler_id.isdigit():
                raise ValueError("Unexpected scheduler job ID")
            row["scheduler_id"] = scheduler_id
            self.persist(row)
        else:
            threading.Thread(target=self.run_local, args=(row, command, folder), daemon=True).start()
        return self.result(job_id)

    def run_local(self, row, command, folder):
        with (folder / "stdout.log").open("wb") as stdout, (folder / "stderr.log").open("wb") as stderr:
            try:
                environment = {k: v for k, v in os.environ.items() if k != "HIGHZYME_COMPUTE_TOKEN"}
                environment["OMP_NUM_THREADS"] = str(row["cores"])
                with self.lock:
                    if row["status"] == "cancelled":
                        return
                    process = subprocess.Popen(command, cwd=folder, env=environment, stdout=stdout, stderr=stderr, start_new_session=os.name != "nt")
                    row.update(process=process, status="running")
                    self.persist(row)
                try:
                    code = process.wait(timeout=row["timeout_seconds"])
                    if row["status"] != "cancelled":
                        row.update(status="completed" if code == 0 else "failed", exit_code=code)
                except subprocess.TimeoutExpired:
                    self.stop_process(process)
                    row["status"] = "timed_out"
            except Exception as exc:
                row.update(status="failed", error=str(exc))
            finally:
                row.pop("process", None)
                row["finished_at"] = time.time()
                self.persist(row)

    @staticmethod
    def stop_process(process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            process.kill()

    def result(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise ValueError("Unknown job")
            row = self.jobs[job_id]
            folder = self.root / job_id
            if row.get("scheduler_id") and row["status"] in ("queued", "running"):
                code_file = folder / ".exit-code"
                if code_file.exists():
                    code = int(code_file.read_text().strip())
                    row.update(status="completed" if code == 0 else "failed", exit_code=code)
                else:
                    query = subprocess.run(["squeue", "-h", "-j", row["scheduler_id"], "-o", "%T"], capture_output=True, text=True, timeout=15, check=True)
                    status = query.stdout.strip()
                    row["status"] = "running" if status == "RUNNING" else "queued" if status else "ended_without_result"
                self.persist(row)
            result = {k: v for k, v in row.items() if k != "process"}
            for name in ("stdout", "stderr"):
                file = folder / (name + ".log")
                if file.exists():
                    with file.open("rb") as stream:
                        stream.seek(max(0, file.stat().st_size - 65536))
                        result[name] = stream.read().decode("utf-8", errors="replace")
            result["files"] = [str(p.relative_to(folder)).replace("\\", "/") for p in folder.rglob("*") if p.is_file() and not p.is_symlink()]
            return result

    def cancel(self, job_id):
        row = self.jobs.get(job_id)
        if not row:
            raise ValueError("Unknown job")
        if row["status"] not in ("queued", "running"):
            return self.result(job_id)
        with self.lock:
            row["status"] = "cancelled"
            process = row.get("process")
        if row.get("scheduler_id"):
            subprocess.run(["scancel", row["scheduler_id"]], timeout=20, check=True)
        elif process:
            self.stop_process(process)
        self.persist(row)
        return self.result(job_id)

    def output_file(self, job_id, name):
        if job_id not in self.jobs:
            raise ValueError("Unknown job")
        file = child_path(self.root / job_id, name)
        if file.stat().st_size > 32 * 1024 ** 2:
            raise ValueError("Output exceeds 32 MiB; retrieve directly from your compute storage")
        data = file.read_bytes()
        return {"file": name, "bytes": len(data), "data": base64.b64encode(data).decode("ascii")}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def dispatch(self):
        if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + self.server.token):
            return self.reply(401, {"error": "Unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 8 * 1024 * 1024:
                raise ValueError("Request exceeds 8 MiB")
            body = json.loads(self.rfile.read(length)) if length else {}
            url = urlsplit(self.path)
            if re.fullmatch(r"/jobs/job_[a-f0-9]{32}/file", url.path) and self.command == "GET":
                result = self.server.output_file(url.path.split("/")[2], parse_qs(url.query).get("path", [""])[0])
            elif self.path == "/health" and self.command == "GET":
                result = self.server.health()
            elif self.path == "/jobs" and self.command == "POST":
                result = self.server.submit(body)
            elif re.fullmatch(r"/jobs/job_[a-f0-9]{32}", self.path) and self.command == "GET":
                result = self.server.result(self.path.split("/")[2])
            elif re.fullmatch(r"/jobs/job_[a-f0-9]{32}/cancel", self.path) and self.command == "POST":
                result = self.server.cancel(self.path.split("/")[2])
            else:
                return self.reply(404, {"error": "Not found"})
            self.reply(200, result)
        except Exception as exc:
            self.reply(400, {"error": str(exc)})

    def reply(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--scheduler", choices=("local", "slurm"), default="local")
    parser.add_argument("--partition", default="")
    args = parser.parse_args()
    server = ComputeServer(("127.0.0.1", args.port), args.root, os.environ.get("HIGHZYME_COMPUTE_TOKEN", ""), args.scheduler, args.partition)
    print(f"mat-agent compute connector: http://127.0.0.1:{server.server_port} ({args.scheduler})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
