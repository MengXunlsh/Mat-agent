"""Project-bound PDF rendering and retrieval of explicitly identified publications."""
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit


def render_document(request):
    import pypdfium2 as pdfium
    file = Path(request['file'])
    if file.suffix.lower() != '.pdf' or file.stat().st_size > 32 * 1024**2:
        raise ValueError('Select a PDF no larger than 32 MiB')
    pages, dpi = request['pages'], request.get('dpi', 120)
    if not isinstance(pages, list) or not 1 <= len(pages) <= 4 or len(set(pages)) != len(pages):
        raise ValueError('Select 1 to 4 distinct PDF pages')
    if type(dpi) is not int or not 72 <= dpi <= 180:
        raise ValueError('Rendering DPI must be an integer from 72 to 180')
    prefix = Path(request['output_prefix']); prefix.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    manifest = {'source': request.get('source_label', file.name), 'source_sha256': digest, 'dpi': dpi, 'pages': []}
    files = {}
    with pdfium.PdfDocument(file) as document:
        if any(type(p) is not int or not 1 <= p <= len(document) for p in pages):
            raise ValueError('Choose existing PDF page numbers starting at 1')
        for number in pages:
            page = document[number-1]
            try:
                if page.get_width()*page.get_height()*(dpi/72)**2 > 12_000_000:
                    raise ValueError('Page exceeds the rendering pixel limit; select a lower DPI')
                bitmap = page.render(scale=dpi/72)
                try:
                    image = bitmap.to_pil()
                    target = str(prefix) + '-page-' + str(number) + '.png'
                    image.save(target)
                    manifest['pages'].append({'page': number, 'locator': 'PDF/page[' + str(number) + ']',
                                              'image': Path(target).name, 'width': image.width, 'height': image.height})
                    files['page_' + str(number)] = target
                finally:
                    bitmap.close()
            finally:
                page.close()
    files['manifest'] = str(prefix) + '-manifest.json'
    files['report'] = str(prefix) + '-report.md'
    Path(files['manifest']).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# ' + ('文献页面' if request.get('language') == 'zh' else 'Document pages'), '', manifest['source'], '']
    lines += ['- PDF/page[' + str(item['page']) + ']: [' + item['image'] + '](' + item['image'] + ')' for item in manifest['pages']]
    Path(files['report']).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return {'source': manifest['source'], 'source_sha256': digest, 'pages': manifest['pages'], 'files': files,
            'next_step': 'Use native read_image on the rendered pages with the selected image-capable model; rendering itself does not interpret the page.'}


def publication_source(value):
    if not isinstance(value, str):
        raise ValueError('Supply an explicit DOI or publication identifier')
    if value.startswith('https://'):
        url = urlsplit(value)
        if url.hostname not in ('doi.org', 'dx.doi.org') or url.query or url.fragment:
            raise ValueError('Use a DOI link, a bare DOI, PMC:PMCID or MED:PMID')
        value = unquote(url.path.lstrip('/'))
    from highzyme.evidence.public_literature import PublicLiteratureClient
    PublicLiteratureClient._identifier_query(value)
    return value


def retrieve_publication(request):
    from highzyme.evidence.public_literature import PublicLiteratureClient, _network_transport
    from highzyme.evidence.public_supplements import PublicSupplementsClient
    source = publication_source(request['source'])
    prefix = Path(request['output_prefix']); prefix.parent.mkdir(parents=True, exist_ok=True)
    provenance, fetched = [], {}
    def transport(url, timeout, max_bytes):
        raw = _network_transport(url, timeout, max_bytes); fetched[url] = raw; return raw
    client = PublicLiteratureClient(transport=transport)
    selected = request.get('document_id', 'article')
    files = {'manifest': str(prefix) + '-manifest.json', 'report': str(prefix) + '-report.md'}
    if selected not in ('article', 'supplements'):
        _, kind, doi = client._identifier_query(source)
        if kind != 'DOI':
            raise ValueError('Supply the parent DOI when selecting a supplement file')
        document, raw = PublicSupplementsClient().document_bytes(doi, selected, provenance)
        files['source'] = str(prefix) + '-source.pdf'
        Path(files['source']).write_bytes(raw)
        metadata = {'doi': doi, 'title': document.get('title') or selected}
        access, units = 'PUBLIC_SUPPLEMENT_PDF_DOWNLOADED', []
        outline = []
    else:
        loaded = client._structured_document(source, selected, provenance)
        if not loaded:
            raise ValueError('No accessible content was found for this publication identifier')
        metadata, document = loaded['metadata'], loaded['document']
        access, units, outline = loaded['access_level'], loaded['units'], loaded['outline']
        files['source'] = str(prefix) + '-source.md'
        lines = ['# ' + str(metadata.get('title') or source), '', 'Source: ' + source, 'Access: ' + access, '']
        for unit in units:
            lines += ['## ' + unit['locator'], '', unit['text'], '']
        if selected == 'supplements':
            lines += ['- ' + json.dumps(row, ensure_ascii=False) for row in outline]
        Path(files['source']).write_text('\n'.join(lines), encoding='utf-8')
        xml = next((raw for url, raw in fetched.items() if url.endswith('/fullTextXML')), None)
        if xml is not None:
            files['original'] = str(prefix) + '-source.xml'; Path(files['original']).write_bytes(xml)
    manifest = {'source_id': source, 'document_id': selected, 'metadata': metadata, 'document': document,
                'access_level': access, 'provenance': provenance, 'available_documents': outline if selected == 'supplements' else [],
                'saved_source_sha256': hashlib.sha256(Path(files['source']).read_bytes()).hexdigest()}
    Path(files['manifest']).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    zh = request.get('language') == 'zh'
    report = ['# ' + str(metadata.get('title') or source), '', source, '',
              ('获取内容：' if zh else 'Retrieved content: ') + access, '',
              '[' + Path(files['source']).name + '](' + Path(files['source']).name + ')']
    if access == 'ABSTRACT_READ':
        report += ['', '本次获取的是摘要。' if zh else 'The retrieved text is the abstract.']
    Path(files['report']).write_text('\n'.join(report) + '\n', encoding='utf-8')
    return {'metadata': metadata, 'access_level': access, 'units_saved': len(units),
            'documents': manifest['available_documents'], 'files': files}
