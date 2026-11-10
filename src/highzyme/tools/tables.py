"""Bounded project-table reading shared by previews and quantitative analysis."""
from contextlib import contextmanager
import csv
from pathlib import Path


@contextmanager
def table_rows(file, sheet=None):
    file = Path(file)
    if file.stat().st_size > 32 * 1024**2:
        raise ValueError('Table exceeds 32 MiB')
    if file.suffix.lower() in ('.csv', '.tsv'):
        with file.open(encoding='utf-8-sig', newline='') as stream:
            yield csv.reader(stream, delimiter='\t' if file.suffix.lower() == '.tsv' else ','), []
    elif file.suffix.lower() == '.xlsx':
        from openpyxl import load_workbook
        book = load_workbook(file, read_only=True, data_only=True)
        try:
            if sheet is not None and sheet not in book.sheetnames:
                raise ValueError('Unknown sheet; choose one of: ' + ', '.join(book.sheetnames))
            yield book[sheet or book.sheetnames[0]].iter_rows(values_only=True), book.sheetnames
        finally:
            book.close()
    else:
        raise ValueError('Supported tables: CSV, TSV, XLSX')


def read_table(file, sheet=None, *, preview=False):
    with table_rows(file, sheet) as (stream, sheets):
        rows = []
        truncated = False
        for row in stream:
            if not any(value is not None and str(value).strip() for value in row):
                continue
            if preview and len(rows) == 9:
                truncated = True
                break
            if len(rows) > 5000:
                raise ValueError('Supply a header and 1 to 5000 nonempty data rows')
            rows.append(list(row))
    if len(rows) < 2:
        raise ValueError('Supply a header and at least one nonempty data row')
    headers = [str(value).strip() if value is not None else '' for value in rows[0]]
    if not all(headers) or len(set(headers)) != len(headers):
        raise ValueError('Column headers must be nonempty and unique')
    if any(len(row) != len(headers) for row in rows[1:]):
        raise ValueError('Each data row must match the header column count')
    return headers, rows[1:], sheets, truncated


def inspect_table(request):
    headers, rows, sheets, truncated = read_table(request['file'], request.get('sheet'), preview=True)
    return {'columns': headers, 'rows': None if truncated else len(rows), 'row_count_exact': not truncated,
            'sheets': sheets, 'preview': [[None if v is None else str(v) for v in row] for row in rows],
            'preview_sheet': request.get('sheet') or (sheets[0] if sheets else None), 'truncated': truncated}
