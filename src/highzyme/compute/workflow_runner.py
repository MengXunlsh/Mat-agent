"""Generate a portable batch script; QE compute nodes need no Python runtime."""
import shlex


def build_runner(manifest):
    lines = ['#!/bin/bash', 'set -eu', 'completed=""', 'mkdir -p shared', '''
emit_status() {
  local state="$1" stage="$2" status="$3" error="$4" rows="$completed"
  if [ -n "$stage" ]; then
    [ -z "$rows" ] || rows="$rows,"
    rows="$rows{\\"id\\":\\"$stage\\",\\"status\\":\\"$status\\"}"
  fi
  printf '{"status":"%s","stages":[%s],"error":"%s"}\\n' "$state" "$rows" "$error" > workflow-status.json
}
mpi=()
if [ "${HIGHZYME_MPI_RANKS:-1}" -gt 1 ]; then
  read -r -a mpi <<< "${HIGHZYME_MPI_COMMAND:-srun}"
  mpi+=( -n "$HIGHZYME_MPI_RANKS" )
fi
run_parallel() {
  if [ "${HIGHZYME_MPI_RANKS:-1}" -gt 1 ]; then "${mpi[@]}" "$@"; else "$@"; fi
}
''']
    for stage in manifest['stages']:
        name, folder = stage['id'], shlex.quote(stage['folder'])
        command = [manifest['programs'][stage['program']]] + stage.get('arguments', [])
        program = ' '.join(shlex.quote(str(value)) for value in command)
        if stage['program'] in ('pw', 'neb'):
            program = 'run_parallel ' + program
        source = shlex.quote(stage['input']) if stage.get('input') else '/dev/null'
        output = shlex.quote(stage['output'])
        lines += ['mkdir -p ' + folder, 'emit_status running ' + name + ' running ""',
                  'if (cd ' + folder + ' && ' + program + ' < ' + source + ' > ' + output + ' 2>&1); then code=0; else code=$?; fi',
                  'if [ "$code" -ne 0 ]; then emit_status failed ' + name + ' failed "' + name + ': program exited with code $code"; exit "$code"; fi']
        tests = []
        if stage['program'] == 'pw':
            tests += ["grep -q 'JOB DONE.' " + output, "! grep -q 'convergence NOT achieved' " + output]
            if stage['calculation'] in ('scf', 'relax', 'vc-relax'):
                tests.append("grep -q 'convergence has been achieved' " + output)
            if stage['calculation'] in ('relax', 'vc-relax'):
                tests.append("grep -Ei -q 'End of BFGS Geometry Optimization|bfgs converged' " + output)
        if stage['program'] == 'neb':
            tests.append("grep -Ei -q 'neb:[[:space:]]*convergence achieved' " + output)
        tests += ['compgen -G ' + shlex.quote(pattern) + ' > /dev/null' for pattern in stage.get('outputs', [])]
        if tests:
            lines += ['if ! (cd ' + folder + '; ' + ' && '.join(tests) + '); then emit_status failed ' + name + ' failed "' + name + ': required convergence or output missing"; exit 1; fi']
        lines += ['[ -z "$completed" ] || completed="$completed,"',
                  'completed="$completed{\\"id\\":\\"' + name + '\\",\\"status\\":\\"completed\\"}"']
    lines += ['emit_status completed "" "" ""']
    return '\n'.join(lines) + '\n'
