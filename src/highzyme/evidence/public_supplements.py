"""Public ACS Figshare supplements with exact parent DOI binding.

Only official public discovery and verified PDF files are fetched. No local
files, account endpoints, credentials, link-only files or content uploads.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import re
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_URL = "https://api.figshare.com/v2"
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 300
MAX_EXTRACTED_CHARS = 4 * 1024 * 1024
MAX_DOCUMENTS = 20
_DOI = re.compile(r"10\.\d{4,9}/[^\s\"<>\\]+", re.I)
_DOCUMENT = re.compile(r"SI:ACS:([1-9]\d{0,19}):([1-9]\d{0,5}):([1-9]\d{0,19})")


def _allowed_url(url, *, redirected=False):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
        return False
    if parsed.hostname == "api.figshare.com":
        return not redirected and bool(re.fullmatch(r"/v2/articles(?:/search|/[1-9]\d*(?:/versions/[1-9]\d*)?)", parsed.path))
    if parsed.hostname == "ndownloader.figshare.com":
        return bool(re.fullmatch(r"/files/[1-9]\d*", parsed.path)) and not parsed.query
    # The official downloader redirects to its ACS storage bucket. This is only
    # permitted as a redirect from the verified download, never as an input URL.
    if redirected and parsed.hostname == "s3-eu-west-1.amazonaws.com":
        return bool(re.match(r"^/pstorage-acs-[a-z0-9-]+/[A-Za-z0-9_./%-]+$", parsed.path))
    return False


class _PublicRedirect(HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if (urlsplit(req.full_url).hostname == "api.figshare.com" or self.count > 3
                or not _allowed_url(newurl, redirected=True)):
            raise ValueError("Redirect outside verified public ACS file storage")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _transport(url, timeout, max_bytes, body=None):
    if not _allowed_url(url):
        raise ValueError("Destination outside the official public supplement endpoints")
    headers = {"User-Agent": "Highzyme-PublicEvidence/1.0", "Accept": "application/json, application/pdf"}
    if body is not None:
        if url != API_URL + "/articles/search":
            raise ValueError("Only public bibliographic search accepts POST")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers)
    deadline = time.monotonic() + timeout
    with build_opener(_PublicRedirect()).open(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError("Response exceeds byte limit")
        blocks, count = [], 0
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("Response deadline exceeded")
            block = response.read(min(65536, max_bytes + 1 - count))
            if not block:
                return b"".join(blocks)
            count += len(block)
            if count > max_bytes:
                raise ValueError("Response exceeds byte limit")
            blocks.append(block)


class PublicSupplementsClient:
    def __init__(self, timeout=20, transport=None, cutoff_date=None):
        self.timeout = float(timeout)
        if not 0 < self.timeout <= 60:
            raise ValueError("timeout must be in (0, 60]")
        self.transport = transport or _transport
        self.cutoff = None  # Legacy keyword is accepted; dates do not restrict discovery or reading.

    def _fetch(self, url, kind, provenance, body=None, max_bytes=MAX_METADATA_BYTES):
        if not _allowed_url(url):
            raise ValueError("Unapproved public endpoint")
        record = {"requested_url": url, "requested_at_utc": datetime.now(timezone.utc).isoformat(),
                  "content_kind": kind, "method": "POST" if body is not None else "GET", "status": "GET_FAILED"}
        provenance.append(record)
        try:
            raw = self.transport(url, self.timeout, max_bytes, body)
            if not isinstance(raw, bytes) or len(raw) > max_bytes:
                raise ValueError("Transport must return bounded bytes")
            record.update(status="FETCHED", retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                          sha256=hashlib.sha256(raw).hexdigest(), response_bytes=len(raw))
            return raw
        except Exception as exc:
            record.update(error_type=type(exc).__name__, failed_at_utc=datetime.now(timezone.utc).isoformat())
            raise

    @staticmethod
    def _doi(value):
        if not isinstance(value, str) or len(value) > 250 or not _DOI.fullmatch(value):
            raise ValueError("A bare public parent DOI is required")
        return value.lower()

    def _verified_item(self, row, doi):
        public_url = urlsplit(str(row.get("url_public_html") or ""))
        if public_url.scheme != "https" or public_url.hostname != "acs.figshare.com" or public_url.username:
            raise ValueError("Supplement is not an ACS public repository item")
        related = row.get("related_materials") or []
        bound = any(isinstance(item, dict) and item.get("identifier_type") == "DOI"
                    and item.get("relation") == "IsSupplementTo"
                    and str(item.get("identifier", "")).lower() == doi for item in related)
        legacy_doi = str(row.get("resource_doi") or "").lower()
        if not bound and legacy_doi != doi:
            raise ValueError("SI parent DOI binding cannot be verified")
        if legacy_doi and legacy_doi != doi:
            raise ValueError("Conflicting SI parent DOI binding")
        if row.get("is_confidential") or row.get("is_embargoed"):
            raise ValueError("Confidential or embargoed documents are unavailable")
        item_id, version = row.get("id"), row.get("version")
        if type(item_id) is not int or item_id <= 0 or type(version) is not int or version <= 0:
            raise ValueError("Invalid public document version")
        return "RELATED_MATERIALS_IS_SUPPLEMENT_TO" if bound else "RESOURCE_DOI_EXACT"

    def _documents(self, row, doi):
        binding = self._verified_item(row, doi)
        files = row.get("files", [])
        if not isinstance(files, list):
            raise ValueError("Invalid public files metadata")
        documents = []
        for file in files[:MAX_DOCUMENTS]:
            if not isinstance(file, dict) or file.get("is_link_only") is not False:
                continue
            file_id, size = file.get("id"), file.get("size")
            name = str(file.get("name") or "")
            if (type(file_id) is not int or file_id <= 0 or type(size) is not int
                    or not 0 < size <= MAX_PDF_BYTES or not name.lower().endswith(".pdf")):
                continue
            url = str(file.get("download_url") or "")
            if url != "https://ndownloader.figshare.com/files/" + str(file_id):
                continue
            docs_id = f"SI:ACS:{row['id']}:{row['version']}:{file_id}"
            documents.append({"document_id": docs_id, "locator": None, "kind": "supplement_document",
                "label": name[:300], "filename": name[:300], "file_bytes": size,
                "parent_doi": doi, "identity_verified": True, "binding": binding,
                "title": str(row.get("title") or "")[:600], "si_doi": row.get("doi"),
                "version": row["version"], "published_date": row["published_date"],
                "url": row["url_public_html"], "download_url": url,
                "license": {"status": "SUPPLEMENT_LICENSE_REPORTED", **(row.get("license") or {})},
                "page_count": None, "read": False, "text_only": True})
        return documents

    def discover(self, parent_doi, provenance):
        doi = self._doi(parent_doi)
        # This POST is an unauthenticated public metadata search, never upload.
        body = json.dumps({"resource_doi": doi, "page": 1, "page_size": MAX_DOCUMENTS}).encode()
        raw = self._fetch(API_URL + "/articles/search", "public_supplement_discovery", provenance, body)
        candidates = json.loads(raw)
        if not isinstance(candidates, list):
            raise ValueError("Invalid public search structure")
        documents = []
        for candidate in candidates[:MAX_DOCUMENTS]:
            identifier = candidate.get("id") if isinstance(candidate, dict) else None
            if type(identifier) is not int or identifier <= 0:
                continue
            raw = self._fetch(API_URL + "/articles/" + str(identifier), "public_supplement_metadata", provenance)
            row = json.loads(raw)
            try:
                if not isinstance(row, dict) or row.get("id") != identifier:
                    raise ValueError("Public item identity mismatch")
                documents.extend(self._documents(row, doi))
            except ValueError:
                # Wrong DOI/host/date is a rejected discovery hit, never evidence.
                provenance[-1]["identity_status"] = "REJECTED_PUBLIC_SUPPLEMENT"
            if len(documents) >= MAX_DOCUMENTS:
                break
        return documents[:MAX_DOCUMENTS]

    def document_bytes(self, parent_doi, document_id, provenance):
        """Verified public PDF bytes, shared by text and native vision readers."""
        doi = self._doi(parent_doi)
        match = _DOCUMENT.fullmatch(document_id) if isinstance(document_id, str) else None
        if not match:
            raise ValueError("Use only an ACS document_id returned by the public SI catalog")
        item_id, version, file_id = (int(value) for value in match.groups())
        raw = self._fetch(f"{API_URL}/articles/{item_id}/versions/{version}",
                          "public_supplement_version_metadata", provenance)
        row = json.loads(raw)
        if row.get("id") != item_id or row.get("version") != version:
            raise ValueError("Public SI item version identity mismatch")
        document = next((doc for doc in self._documents(row, doi) if doc["document_id"] == document_id), None)
        if document is None:
            raise ValueError("The requested public PDF is absent, unbound or unavailable")
        raw = self._fetch(document["download_url"], "public_supplement_pdf", provenance,
                          max_bytes=MAX_PDF_BYTES)
        if len(raw) != document["file_bytes"] or not raw.startswith(b"%PDF-"):
            raise ValueError("Public PDF bytes do not match the verified file metadata")
        document = {**document, 'id': document_id, 'sha256': hashlib.sha256(raw).hexdigest()}
        return document, raw

    def read_document(self, parent_doi, document_id, provenance):
        document, raw = self.document_bytes(parent_doi, document_id, provenance)
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(raw), strict=True)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF cannot be read by the public text reader")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError("Public PDF exceeds page parsing limit")
        units, extracted_chars = [], 0
        deadline = time.monotonic() + self.timeout
        for index, page in enumerate(reader.pages, 1):
            # Local text extraction only, no PDF execution, OCR, external service
            # or inferred graph values. Empty pages remain visible in the outline.
            text = page.extract_text() or ""
            if not text.strip():
                text = ""
            extracted_chars += len(text)
            if extracted_chars > MAX_EXTRACTED_CHARS:
                raise ValueError("Public PDF exceeds text extraction character limit")
            if time.monotonic() > deadline:
                raise TimeoutError("Public PDF text extraction deadline exceeded")
            units.append({"locator": f"pdf/page[{index}]", "kind": "pdf_page_text",
                          "section": "Supporting information", "label": f"PDF page {index}",
                          "physical_page": index, "text": text, "text_only": True,
                          "extraction_status": "TEXT_EXTRACTED" if text.strip() else "NO_EXTRACTABLE_TEXT"})
        document = {**document, "id": document_id, "kind": "PUBLIC_SUPPLEMENT_PDF",
                    "sha256": hashlib.sha256(raw).hexdigest(), "page_count": len(reader.pages),
                    "text_only": True}
        document.pop("read", None)
        return document, units
