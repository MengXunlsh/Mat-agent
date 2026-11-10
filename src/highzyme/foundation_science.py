"""Small JSON bridge reusing Highzyme's existing scientific readers.

The Harness extension supplies trusted paths after applying project grants.
No model, database write or remote computation is performed here.
"""
import hashlib
import json
from pathlib import Path
import sys


def run(request):
    action = request['action']
    if action == 'read_dataset_record':
        from highzyme.dataset_runtime import record_summary
        record = json.loads(Path(request['file']).read_text(encoding='utf-8-sig'))
        if record.get('schema') != 'highzyme.dataset-record.v1':
            raise ValueError('Select a saved dataset record; use the text view for other files')
        fields = request.get('fields')
        if fields is not None:
            available = {o['field'] for o in record['observations']}
            record['observations'] = [o for o in record['observations'] if any(o['field'] == f or o['field'].startswith(f + '.') for f in fields)]
            record['unknown_fields'] = [f for f in fields if not any(name == f or name.startswith(f + '.') for name in available)]
            record['selected_fields'] = fields
            record['coverage'] = {**record.get('coverage', {}), 'source_observations_returned': record.get('coverage', {}).get('observations_returned'),
                                  'observations_returned': len(record['observations']), 'observations_selected': len(record['observations'])}
        return record if request.get('detail') == 'full' else record_summary(record)
    if action == 'candidate_check':
        from highzyme.tools.candidate_checks import check_candidate
        return check_candidate(request)
    if action == 'choose_file':
        from highzyme.infrastructure.file_dialogs import choose_file
        return choose_file(request['kind'])
    if action == 'result_view':
        from highzyme.tools.result_views import result_view
        return result_view(request)
    if action == 'structure_view':
        from highzyme.tools.result_views import structure_view
        return structure_view(request['text'].encode('utf-8'), request['name'])
    if action == 'calculation':
        from highzyme.tools.project_calculations import calculate
        return calculate(request)
    if action == 'replot_analysis':
        from highzyme.tools.analysis_outputs import replot_analysis
        return replot_analysis(request)
    if action == 'render_document':
        from highzyme.evidence.project_documents import render_document
        return render_document(request)
    if action == 'retrieve_publication':
        from highzyme.evidence.project_documents import retrieve_publication
        return retrieve_publication(request)
    if action in ('save_evidence', 'compare_evidence'):
        from highzyme.tools.research_evidence import save_evidence, compare_evidence
        return save_evidence(request) if action == 'save_evidence' else compare_evidence(request)
    if action == 'replot_kinetics':
        from highzyme.tools.initial_rate import replot_fit
        return replot_fit(request)
    if action in ('inspect_table', 'fit_kinetics'):
        from highzyme.tools.initial_rate import inspect_table, export_fit
        return inspect_table(request) if action == 'inspect_table' else export_fit(request)
    if action == 'identity':
        from highzyme.tools.chemistry import formula_info, molecule_info
        value = formula_info(request['formula']) if request.get('formula') else molecule_info(request['smiles'])
        if request.get('output_prefix'):
            from highzyme.tools.result_views import export_identity
            return export_identity(value, request)
        return value
    if action == 'structure':
        from highzyme.tools.nanozyme_structures import parse_nanozyme_structure
        file = Path(request['file'])
        if file.stat().st_size > 32 * 1024**2:
            raise ValueError('Structure file exceeds 32 MiB')
        value = parse_nanozyme_structure(file.read_bytes(), file.name)
        value['atom_count'] = len(value['symbols'])
        # Coordinates remain in the source file; the prompt gets its summary.
        return {k:v for k,v in value.items() if k not in ('symbols', 'positions_angstrom', 'fractional_positions', 'atom_labels', 'occupancies')}
    if action == 'document':
        from highzyme.evidence.local_documents import LocalDocumentStore
        file, root = Path(request['file']), Path(request['root'])
        if file.stat().st_size > 32 * 1024**2:
            raise ValueError('Document exceeds 32 MiB')
        entry = {'document_id': 'project-file', 'path': file.relative_to(root).as_posix(), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                 'title': file.name, 'permissions': {'read': True, 'share_with_agent': True}}
        store = LocalDocumentStore(root, registry_data={'schema': 'highzyme.local_documents.v1', 'documents': [entry]})
        return store.agent_projection(store.read('project-file', start=request.get('start', 1), end=request.get('end'), share_with_agent=True))
    raise ValueError('Unknown scientific operation')


def main():
    try:
        result = run(json.load(sys.stdin))
        print(json.dumps({'result': result}, ensure_ascii=False, allow_nan=False))
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
