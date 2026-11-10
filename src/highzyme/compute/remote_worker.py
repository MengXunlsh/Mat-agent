"""Short-lived Slurm operations, sent through SSH; compatible with Python 3.6+."""
import base64
import getpass
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time


def run(args):
    try:
        process = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 universal_newlines=True, timeout=30)
    except FileNotFoundError as error:
        return 127, "", str(error)
    return process.returncode, process.stdout.strip(), process.stderr.strip()


def inspect(profile, detailed=True):
    root = os.path.expanduser(profile.get("remote_root") or "~/.highzyme/jobs")
    parent = root
    while not os.path.exists(parent):
        parent = os.path.dirname(parent)
    commands = {name: shutil.which(name) for name in ("sbatch", "squeue", "scancel", "sacct")}
    partitions = []
    associations = []
    if commands["sbatch"] and detailed:
        code, output, _ = run(["sinfo", "-h", "-o", "%P|%a"])
        if code == 0:
            partitions = [dict(zip(("name", "state"), line.replace("*", "").split("|")))
                          for line in output.splitlines()[:80] if "|" in line]
        code, output, _ = run(["sacctmgr", "-nP", "show", "assoc", "where",
                               "user=" + getpass.getuser(), "format=Account,Partition,QOS"])
        if code == 0:
            associations = [dict(zip(("account", "partition", "qos"), line.split("|")[:3]))
                            for line in output.splitlines()[:30]]
    setup = profile.get("setup_script", "")
    requested = {"quantum_espresso": profile.get("qe_command") or "pw.x"}
    for name in ("dos", "projwfc", "bands", "pp", "neb", "bader"):
        requested[name] = profile.get("program_commands", {}).get(name) or (name + ".x" if name != "bader" else "bader")
    script = setup + '\n' + '\n'.join('printf "__HZ__' + name + '|%s\\n" "$(command -v ' + shlex.quote(command) + ' || true)"' for name, command in requested.items())
    code, output, error = run(["bash", "-lc", script])
    programs = {name: None for name in requested}
    for line in output.splitlines():
        if line.startswith('__HZ__'):
            name, value = line[6:].split('|', 1)
            programs[name] = value or None
    qe = programs['quantum_espresso']
    _, modules, module_error = run(["bash", "-lc", "module -t avail 2>&1"]) if detailed else (0, '', '')
    available = re.findall(r"[^\s()]+(?:quantum[_-]?espresso|espresso)[^\s()]*", modules + "\n" + module_error, re.I)
    python_command = shlex.quote(profile.get("python_command") or "python3")
    python_code, python_version, _ = run(["bash", "-lc", setup + "\n" + python_command + " --version"])
    capabilities = ["shell"] + (["python"] if python_code == 0 else []) + (["quantum_espresso"] if qe else [])
    scheduler_ready = all(commands[name] for name in ("sbatch", "squeue", "scancel"))
    writable = os.access(parent, os.W_OK)
    issues = []
    if not scheduler_ready:
        issues.append("Slurm commands are unavailable: " + ", ".join(name for name in ("sbatch", "squeue", "scancel") if not commands[name]))
    if not writable:
        issues.append("Remote working directory is not writable")
    if profile.get("partition") and partitions and not any(p["name"] == profile["partition"] and p["state"] == "up" for p in partitions):
        issues.append("Selected Slurm partition is unavailable: " + profile["partition"])
    return {"protocol": "highzyme-compute-v1", "connected": True, "scheduler": "slurm" if scheduler_ready else None,
            "home": os.path.expanduser("~"), "remote_root": root, "writable": writable,
            "checks": {"ssh": True, "scheduler": scheduler_ready, "workdir": writable, "quantum_espresso": bool(qe)}, "issues": issues,
            "capabilities": capabilities, "programs": programs, "python_version": python_version if python_code == 0 else None, "partitions": partitions,
            "associations": associations, "qe_modules": sorted(set(available))[:40],
            "analysis_modules": sorted(set(re.findall(r'[^\s()]+(?:bader|critic2)[^\s()]*', modules + '\n' + module_error, re.I)))[:30],
            "environment_error": error if not qe and setup else None,
            "ready": not issues}


def write_record(folder, value):
    with open(os.path.join(folder, "job.json"), "w") as stream:
        json.dump(value, stream, indent=2)


def submit(request):
    folder, profile, task = request["folder"], request["profile"], request["task"]
    entry = "task.py" if task["capability"] == "python" else "task.sh"
    with open(os.path.join(folder, entry), "w", encoding="utf-8") as stream:
        stream.write(task["script"])
    command = (shlex.quote(profile.get("python_command") or "python3") + " " + entry
               if entry.endswith(".py") else "bash " + entry)
    ranks, threads = task["ranks"], task["threads"]
    if ranks > 1 and task.get("launch_mode") != "workflow":
        command = (profile.get("mpi_command") or "srun") + " -n " + str(ranks) + " " + command
    wrapper = "#!/bin/bash\nset -e\ncd " + shlex.quote(folder) + "\n"
    wrapper += "export OMP_NUM_THREADS=" + str(threads) + "\nexport MKL_NUM_THREADS=" + str(threads) + "\nexport PYTHONIOENCODING=utf-8\n"
    wrapper += "export HIGHZYME_MPI_RANKS=" + str(ranks) + "\nexport HIGHZYME_MPI_COMMAND=" + shlex.quote(profile.get("mpi_command") or "srun") + "\n"
    wrapper += profile.get("setup_script", "") + "\n" + command + "\n"
    with open(os.path.join(folder, "submit.sh"), "w", encoding="utf-8") as stream:
        stream.write(wrapper)
    args = ["sbatch", "--parsable", "--job-name", "highzyme-" + request["id"][-8:],
            "--chdir", folder, "--ntasks", str(ranks), "--cpus-per-task", str(threads),
            "--time", str(max(1, (task["timeout_seconds"] + 59) // 60)),
            "--mem", str(task["memory_mb"]), "--output", os.path.join(folder, "stdout.log"),
            "--error", os.path.join(folder, "stderr.log")]
    for key in ("partition", "account", "qos"):
        if profile.get(key):
            args += ["--" + key, profile[key]]
    code, output, error = run(args + [os.path.join(folder, "submit.sh")])
    if code:
        raise ValueError(error or output)
    scheduler_id = output.split(";")[0]
    if not scheduler_id.isdigit():
        raise ValueError("Slurm did not return a job ID: " + output)
    row = {"id": request["id"], "scheduler_id": scheduler_id, "scheduler": "slurm",
           "status": "queued", "created_at": time.time(), "remote_directory": folder,
           "capability": task["capability"], "resources": {key: task[key] for key in
           ("ranks", "threads", "memory_mb", "timeout_seconds")}}
    write_record(folder, row)
    return row


def status(request):
    folder = request["folder"]
    record_file = os.path.join(folder, 'job.json')
    if os.path.isfile(record_file):
        with open(record_file) as stream:
            row = json.load(stream)
    else:
        row = request['record']
        if not os.path.isfile(os.path.join(folder, 'submit.sh')):
            row.update(status='failed', reason='Submission did not reach the scheduler', files=[])
            return row
        code, output, error = run(['sacct', '-nP', '-S', 'today', '--name', 'highzyme-' + row['id'][-8:], '--format=JobIDRaw,State,ExitCode,WorkDir'])
        match = next((line.split('|') for line in output.splitlines() if len(line.split('|')) >= 4 and line.split('|')[0].isdigit() and line.split('|')[3] == folder), None)
        if code or not match:
            row.update(reason=error or 'Submission outcome is still unknown; no calculation was replayed', files=[])
            return row
        row.update(scheduler_id=match[0], status='queued')
    if request["action"] == "cancel":
        code, output, error = run(["scancel", row["scheduler_id"]])
        if code:
            raise ValueError(error or output)
        row["status"] = "cancelled"
    elif row["status"] not in ("completed", "failed", "cancelled", "timed_out"):
        code, output, error = run(["squeue", "-h", "-j", row["scheduler_id"], "-o", "%T|%R|%M"])
        if code:
            raise ValueError(error or output)
        if output:
            parts = output.split("|")
            state, reason = parts[:2]
            row.update(scheduler_state=state, reason=reason, elapsed=parts[2] if len(parts) > 2 else None, status="running" if state in
                       ("RUNNING", "COMPLETING", "STAGE_OUT") else "queued")
        else:
            code, output, error = run(["sacct", "-nP", "-j", row["scheduler_id"],
                                      "--format=JobIDRaw,State,ExitCode,Elapsed,Reason"])
            if code:
                raise ValueError(error or output)
            main = next((line.split("|") for line in output.splitlines()
                         if line.startswith(row["scheduler_id"] + "|")), None)
            if main:
                state = main[1].split()[0].rstrip("+")
                row.update(scheduler_state=state, exit_code=main[2])
                if len(main) > 3:
                    row["elapsed"] = main[3]
                row["reason"] = main[4] if len(main) > 4 else ""
                row["status"] = ("completed" if state == "COMPLETED" and main[2] == "0:0" else
                                 "cancelled" if state == "CANCELLED" else "timed_out" if state == "TIMEOUT"
                                 else "running" if state == "RUNNING" else "queued" if state == "PENDING" else "failed")
            else:
                row["reason"] = "Waiting for scheduler accounting"
    write_record(folder, row)
    progress = os.path.join(folder, "workflow-status.json")
    if os.path.isfile(progress):
        with open(progress) as stream:
            row["progress"] = json.load(stream)
    for name in ("stdout", "stderr"):
        file = os.path.join(folder, name + ".log")
        if os.path.isfile(file):
            with open(file, "rb") as stream:
                stream.seek(max(0, os.path.getsize(file) - 12000))
                row[name] = stream.read().decode("utf-8", errors="replace")
    row["files"] = []
    for current, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d != 'scratch' and not (d == 'shared' and os.path.isfile(progress)) and not os.path.islink(os.path.join(current, d))]
        row["files"].extend(os.path.relpath(os.path.join(current, f), folder).replace(os.sep, "/")
                            for f in files if not os.path.islink(os.path.join(current, f)))
    return row


if __name__ == "__main__":
    try:
        request = json.loads(base64.b64decode(sys.argv[1]))
        result = inspect(request["profile"], request.get('detailed', True)) if request["action"] == "probe" else submit(request) if request["action"] == "submit" else status(request)
        print(json.dumps({"result": result}))
    except Exception as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
