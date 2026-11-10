"""ASE-based QE input preparation and convergence-aware result import."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import sys


def sha256(file):
    with Path(file).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(request):
    from ase.io import read, write

    atoms = read(request["structure_file"], index=0)
    if not len(atoms) or abs(atoms.cell.volume) < 1e-6:
        raise ValueError("Provide a structure with an explicit non-zero periodic cell")
    atoms.pbc = True
    parameters = request["parameters"]
    if parameters.get("calculation", "scf") not in ("scf", "relax", "vc-relax", "nscf", "bands"):
        raise ValueError("Unsupported PW calculation")
    cutoff = float(parameters["ecutwfc"])
    density_cutoff = float(parameters.get("ecutrho", cutoff * 4))
    kpoints = parameters["kpoints"]
    if not 0 < cutoff <= density_cutoff or len(kpoints) != 3 or any(type(k) is not int or k < 1 for k in kpoints):
        raise ValueError("Supply positive cutoffs in Ry and three positive integer k-point counts")
    symbols = sorted(set(atoms.get_chemical_symbols()))
    if set(symbols) != set(request["pseudopotentials"]):
        raise ValueError("Supply one UPF pseudopotential for every structure element")
    from ase.constraints import FixAtoms, FixCartesian
    constraints = [] if 'fixed_atoms' in parameters or 'fixed_cartesian' in parameters else list(atoms.constraints)
    fixed = parameters.get("fixed_atoms", [])
    if any(type(i) is not int or not 0 <= i < len(atoms) for i in fixed):
        raise ValueError("Fixed atom indices must be zero-based structure indices")
    if fixed:
        constraints.append(FixAtoms(indices=fixed))
    for row in parameters.get("fixed_cartesian", []):
        if not 0 <= row["index"] < len(atoms) or len(row["mask"]) != 3:
            raise ValueError("Invalid Cartesian constraint")
        constraints.append(FixCartesian(row["index"], mask=row["mask"]))
    atoms.set_constraint(constraints)
    if "magnetic_moments" in parameters:
        if len(parameters["magnetic_moments"]) != len(atoms):
            raise ValueError("Supply one initial magnetic moment per atom")
        atoms.set_initial_magnetic_moments(parameters["magnetic_moments"])
    folder = Path(request["directory"])
    folder.mkdir(parents=True, exist_ok=True)
    mapping, inputs, manifest = {}, [], []
    for symbol in symbols:
        source = Path(request["pseudopotentials"][symbol])
        text = source.read_text(encoding="utf-8", errors="replace")[:20000]
        if not (re.search(r'element\s*=\s*["\']\s*' + symbol + r'\s*["\']', text, re.I)
                or re.search(r"^\s*" + symbol + r"\s+Element\s*$", text, re.M)):
            raise ValueError("UPF element mismatch: " + symbol)
        target = symbol.lower() + ".upf"
        mapping[symbol] = target
        destination = folder / "pseudo" / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        inputs.append({"source": str(destination), "target": "pseudo/" + target})
        manifest.append({"element": symbol, "file": target, "sha256": sha256(source)})
    system = dict(parameters.get("system", {}))
    system.update(ecutwfc=cutoff, ecutrho=density_cutoff)
    if constraints:
        system.setdefault('nosym', True)
    control = {"calculation": parameters.get("calculation", "scf"), "prefix": "highzyme", "pseudo_dir": "./pseudo", "outdir": "./scratch", "disk_io": "low"}
    control["outdir"] = request.get("scratch_dir", "./scratch")
    control.update({k: v for k, v in parameters.get("control", {}).items() if k in
                    ("nstep", "etot_conv_thr", "forc_conv_thr", "max_seconds", "tstress", "tprnfor")})
    data = {"control": control, "system": system,
            "electrons": {"conv_thr": 1e-8, "electron_maxstep": 100, **parameters.get("electrons", {})}}
    if control["calculation"] in ("relax", "vc-relax"):
        data["ions"] = parameters.get("ions", {"ion_dynamics": "bfgs"})
    if control["calculation"] == "vc-relax":
        data["cell"] = parameters.get("cell", {"cell_dynamics": "bfgs"})
    kpath = parameters.get("kpath")
    if control["calculation"] == "bands" and not kpath:
        raise ValueError("Band calculations require explicit kpath points with weights")
    if kpath:
        import numpy as np
        kpath = np.asarray(kpath, dtype=float)
        if kpath.ndim != 2 or kpath.shape[1] != 4:
            raise ValueError("kpath must have four columns: kx, ky, kz, weight")
    write(folder / "qe.in", atoms, format="espresso-in", input_data=data,
          pseudopotentials=mapping, kpts=kpath if kpath is not None else tuple(kpoints))
    write(folder / "input.extxyz", atoms)
    record = {"schema": "highzyme.qe.request.v1", "parameters": {**parameters, "calculation": control["calculation"],
              "ecutwfc": cutoff, "ecutrho": density_cutoff, "system": system, "electrons": data["electrons"], "control": control}, "pseudopotentials": manifest,
              "structure": {"formula": atoms.get_chemical_formula(), "atoms": len(atoms),
                            "symbols": atoms.get_chemical_symbols(), "cell_A": atoms.cell.tolist(),
                            "sha256": sha256(request["structure_file"])}}
    (folder / "request.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    inputs.append({"source": str(folder / "qe.in"), "target": "qe.in"})
    for item in inputs:
        item["sha256"] = sha256(item["source"])
    return {"input_files": inputs, "request": record}


def output_history(text):
    iterations, steps = [], []
    cycle = 0
    for line in text.splitlines():
        iteration = re.search(r'iteration\s+#\s*(\d+)', line)
        if iteration:
            number = int(iteration[1])
            if number == 1:
                cycle += 1
            iterations.append(dict(cycle=cycle, iteration=number))
        energy = re.search(r'(?:!\s*)?total energy\s*=\s*([-+\d.EeDd]+)\s+Ry', line)
        accuracy = re.search(r'estimated scf accuracy\s*[<=>]+\s*([-+\d.EeDd]+)\s+Ry', line)
        if iterations and energy:
            iterations[-1]['energy_Ry'] = float(energy[1].replace('D', 'E').replace('d', 'e'))
        if iterations and accuracy:
            iterations[-1]['accuracy_Ry'] = float(accuracy[1].replace('D', 'E').replace('d', 'e'))
        force = re.search(r'Total force\s*=\s*([-+\d.EeDd]+)', line)
        if force:
            steps.append(dict(step=len(steps) + 1, total_force_Ry_bohr=float(force[1].replace('D', 'E').replace('d', 'e')),
                              energy_Ry=iterations[-1].get('energy_Ry') if iterations else None))
    return dict(iterations=iterations, ionic_steps=steps)


def plot_convergence(history, folder, threshold):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from highzyme.tools.figure_style import figure_rc, figure_size, series_style, EXPORT_DPI
    keys = [key for key in ('energy_Ry', 'accuracy_Ry') if any(row.get(key) is not None for row in history['iterations'])]
    if not keys:
        return {}
    with plt.rc_context(figure_rc()):
        fig, axes = plt.subplots(1, len(keys), figsize=figure_size(len(keys)), layout='constrained', squeeze=False)
        for index, (key, ax) in enumerate(zip(keys, axes[0])):
            points = [(i+1, row[key]) for i, row in enumerate(history['iterations']) if row.get(key) is not None]
            style = series_style(index)
            ax.plot([p[0] for p in points], [p[1] for p in points], color=style['color'], marker=style['marker'], markersize=3)
            if key == 'accuracy_Ry':
                ax.set_yscale('log')
                ax.axhline(threshold, color='#6F747B', linestyle='--', linewidth=.8, label='SCF tolerance')
                ax.legend()
            ax.set(xlabel='Electronic iteration', ylabel='Total energy (Ry)' if key == 'energy_Ry' else 'Estimated SCF accuracy (Ry)')
        files = {}
        for fmt in ('png', 'svg'):
            name = 'convergence.' + fmt
            fig.savefig(Path(folder)/name, dpi=EXPORT_DPI)
            files['convergence_' + fmt] = name
        plt.close(fig)
    return files


def collect(request):
    from ase.io import read, write

    folder = Path(request["directory"])
    record = json.loads((folder / "request.json").read_text(encoding="utf-8"))
    output = folder / "qe.out"
    text = output.read_text(encoding="utf-8", errors="replace") if output.exists() else ""
    calculation = record["parameters"].get("calculation", "scf")
    scf = bool(re.search(r"convergence has been achieved", text)) and "convergence NOT achieved" not in text
    geometry = bool(re.search(r"End of BFGS Geometry Optimization|bfgs converged", text, re.I)) if calculation in ("relax", "vc-relax") else None
    done = "JOB DONE." in text
    success = scf and done and (geometry is not False) and request["job"]["status"] == "completed"
    energy = re.findall(r"!\s+total energy\s*=\s*([-+\d.Ee]+)\s+Ry", text)
    version = re.search(r"Program PWSCF\s+v\.(\S+)", text)
    result = {"schema": "highzyme.qe.result.v1", "status": "converged" if success else "not_converged",
              "scf_converged": scf, "geometry_converged": geometry, "job_done": done,
              "energy_Ry": float(energy[-1]) if energy and success else None,
              "version": version[1] if version else None, "request": record,
              "history": output_history(text),
              "job": {key: request["job"].get(key) for key in ("id", "scheduler_id", "status", "exit_code", "resources")}}
    files = {"input": "qe.in", "structure": "input.extxyz", "request": "request.json", "result": "result.json", "report": "report.md"}
    for pseudo in record["pseudopotentials"]:
        files["pseudopotential_" + pseudo["element"].lower()] = "pseudo/" + pseudo["file"]
    for name in ("qe.out", "stdout.log", "stderr.log", "submit.sh"):
        if (folder / name).exists():
            files[name.replace(".", "_")] = name
    if success:
        final = read(output, format="espresso-out", index=-1)
        write(folder / "final.extxyz", final)
        write(folder / "final.cif", final)
        files.update(final_structure="final.extxyz", crystal="final.cif")
    files.update(plot_convergence(result['history'], folder, record['parameters'].get('electrons', {}).get('conv_thr', 1e-8)))
    result["sources"] = {name: sha256(folder / name) for role, name in files.items()
                         if role not in ("result", "report", "convergence_png", "convergence_svg") and (folder / name).exists()}
    (folder / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    zh = request.get("language") == "zh"
    lines = ["# " + ("Quantum ESPRESSO 计算" if zh else "Quantum ESPRESSO calculation"), "",
             ("状态：" + ("已收敛" if success else "未收敛") if zh else "Status: " + result["status"]),
             "", ("- Slurm 任务：" if zh else "- Slurm job: ") + str(result["job"]["scheduler_id"]),
             ("- QE 版本：" if zh else "- QE version: ") + str(result["version"]), ("- 化学式：" if zh else "- Formula: ") + record["structure"]["formula"],
             ("- 电子迭代收敛：" if zh else "- SCF converged: ") + (("是" if scf else "否") if zh else str(scf)),
             ("- 结构优化收敛：" if zh else "- Geometry converged: ") + (str(geometry) if not zh else "未执行" if geometry is None else "是" if geometry else "否"),
             ("- 总能量 (Ry)：" if zh else "- Energy (Ry): ") + str(result["energy_Ry"]), "", "## " + ("参数" if zh else "Parameters"),
             "", "```json", json.dumps(record["parameters"], indent=2), "```", "",
             ("输入、赝势哈希和调度记录见 request.json 与 result.json。" if zh else
              "See request.json and result.json for input, pseudopotential hashes and scheduler records.")]
    if files.get('convergence_svg'):
        lines[2:2] = ['![SCF convergence](convergence.svg)', '']
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"result": result, "files": files}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        print(json.dumps({"result": prepare(request) if request["action"] == "prepare" else collect(request)}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
