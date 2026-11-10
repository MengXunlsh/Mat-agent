"""Read explicitly registered local PDF/DOCX ranges without arbitrary paths.

Registration is a trusted project operation, not an Agent tool. Documents must
carry an exact hash and explicit reading/sharing policy. The reader extracts
text only; figures, scanned pages and equation fidelity are not claimed read.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import threading
from xml.etree import ElementTree as ET
from zipfile import ZipFile

DEFAULT_REGISTRY = "protocol/local-documents.json"
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_TEXT_CHARS = 24000
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stamp(path):
    st = path.stat()
    return st.st_size, st.st_mtime_ns, st.st_ctime_ns


def _registered_path(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError("Registered project-relative document path required")
    path = (root / value).resolve()
    if not path.is_relative_to(root) or any(x in value.casefold() for x in ("sealed", "封存", ".env")):
        raise ValueError("Document path is outside the permitted non-sealed project scope")
    if not path.is_file():
        raise ValueError("Registered local document is unavailable")
    return path


def _paragraph_text(element):
    out = []
    for node in element.iter():
        if node.tag == WORD_NS + "t" and node.text:
            out.append(node.text)
        elif node.tag == WORD_NS + "tab":
            out.append("\t")
        elif node.tag in (WORD_NS + "br", WORD_NS + "cr"):
            out.append("\n")
    return "".join(out).strip()


def _docx_blocks(path):
    with ZipFile(path) as archive:
        info = archive.getinfo("word/document.xml")
        if info.file_size > MAX_DOCUMENT_BYTES:
            raise ValueError("Document XML exceeds bounded reader size")
        raw = archive.read(info)
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("External XML entities are not permitted")
    body = ET.fromstring(raw).find(WORD_NS + "body")
    if body is None:
        return []
    result, paragraph, table = [], 0, 0
    for element in body:
        if element.tag == WORD_NS + "p":
            paragraph += 1
            result.append({"locator": f"word/document.xml/paragraph[{paragraph}]",
                           "text": _paragraph_text(element)})
        elif element.tag == WORD_NS + "tbl":
            table += 1
            for row_no, row in enumerate(element.findall(WORD_NS + "tr"), 1):
                for cell_no, cell in enumerate(row.findall(WORD_NS + "tc"), 1):
                    for para_no, para in enumerate(cell.findall(WORD_NS + "p"), 1):
                        result.append({"locator": f"word/document.xml/table[{table}]/row[{row_no}]/cell[{cell_no}]/paragraph[{para_no}]",
                                       "text": _paragraph_text(para)})
    return result


class LocalDocumentStore:
    """Registry schema: ``{'schema':'highzyme.local_documents.v1', 'documents': [...]}``.

    Each document has ``document_id, path, sha256, title, source_doi`` (optional),
    ``document_role`` (main_text/supporting_information/author_manuscript),
    ``source_kind`` (publisher/author/other), and ``permissions`` with booleans
    ``read`` and ``share_with_agent``. A read request supplies only document ID
    and a bounded 1-based page/block range. Sharing requires both registry policy
    and a trusted per-read grant; neither can be supplied as an Agent tool field.
    """

    def __init__(self, project_root, registry_path=DEFAULT_REGISTRY, *, pdf_extractor=None, max_cache_entries=24, registry_data=None):
        self.root = Path(project_root).resolve()
        self.registry_path = (self.root / str(registry_path)).resolve()
        if not self.registry_path.is_relative_to(self.root):
            raise ValueError("Local document registry must be inside the project")
        self.pdf_extractor = pdf_extractor
        self._provided_registry = deepcopy(registry_data) if registry_data is not None else None
        self.max_cache_entries = max(1, min(int(max_cache_entries), 64))
        self._cache = OrderedDict()
        self._lock = threading.RLock()

    def _registry(self):
        if self._provided_registry is None and not self.registry_path.is_file():
            return {}
        registry = self._provided_registry if self._provided_registry is not None else json.loads(self.registry_path.read_text("utf-8-sig"))
        if registry.get("schema") != "highzyme.local_documents.v1" or not isinstance(registry.get("documents"), list):
            raise ValueError("Invalid local document registry contract")
        documents = {}
        for entry in registry["documents"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("document_id"), str):
                raise ValueError("Local document identity is required")
            if entry["document_id"] in documents or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", entry["document_id"]):
                raise ValueError("Local document identity is invalid or duplicated")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", entry.get("sha256", "")):
                raise ValueError("Registered local document hash is required")
            permissions = entry.get("permissions", {})
            if not isinstance(permissions, dict) or any(not isinstance(permissions.get(k, False), bool)
                                                       for k in ("read", "share_with_agent")):
                raise ValueError("Document permissions must be explicit booleans")
            documents[entry["document_id"]] = entry
        return documents

    def catalog(self):
        with self._lock:
            return {"status": "METADATA_ONLY", "read": False, "documents": [
                {**{k: deepcopy(entry[k]) for k in ("document_id", "title", "source_doi", "document_role", "source_kind", "sha256", "permissions")
                    if k in entry}, 'format': Path(entry.get('path', '')).suffix.lower().lstrip('.')}
                 for entry in self._registry().values()],
                "range_units": {"pdf": "1-based page", "docx": "1-based body/table text block"},
                "limits": {"pdf_pages_per_read": 5, "docx_blocks_per_read": 20, "text_characters_per_read": MAX_TEXT_CHARS}}

    def _pdf_pages(self, path, start, end):
        if self.pdf_extractor is not None:
            pages = self.pdf_extractor(path)
            return len(pages), [{"locator": f"PDF/page[{p}]", "text": pages[p - 1]} for p in range(start, min(end, len(pages)) + 1)]
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("Project PDF text reader is unavailable; no dependencies were installed") from exc
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Encrypted documents require a separately authorized readable version")
        return len(reader.pages), [{"locator": f"PDF/page[{p}]", "text": reader.pages[p - 1].extract_text() or ""}
                                  for p in range(start, min(end, len(reader.pages)) + 1)]

    def read(self, document_id, *, start=1, end=None, share_with_agent=False):
        if not isinstance(document_id, str) or not isinstance(share_with_agent, bool):
            raise ValueError("Document ID and trusted boolean sharing permission required")
        if end is None:
            end = start
        if any(not isinstance(v, int) or isinstance(v, bool) for v in (start, end)) or not 1 <= start <= end:
            raise ValueError("Document range must contain positive 1-based integers")
        with self._lock:
            registry = self._registry()
            if document_id not in registry:
                raise ValueError("Only explicitly registered local document IDs may be read")
            entry = registry[document_id]
            permissions = entry.get("permissions", {})
            if permissions.get("read") is not True:
                raise ValueError("Registered document is not permitted for reading")
            if share_with_agent and permissions.get("share_with_agent") is not True:
                raise ValueError("Registered document is not permitted for Agent sharing")
            path = _registered_path(self.root, entry.get("path"))
            suffix = path.suffix.lower()
            if suffix not in (".pdf", ".docx"):
                raise ValueError("Only registered PDF and DOCX text ranges are supported")
            if end - start + 1 > (5 if suffix == ".pdf" else 20):
                raise ValueError("Requested text range exceeds the per-read limit")
            stamp = _stamp(path)
            if stamp[0] > MAX_DOCUMENT_BYTES:
                raise ValueError("Registered document exceeds the bounded reader size")
            content_hash = _sha256(path)
            if content_hash != entry["sha256"].lower():
                raise ValueError("Registered document hash mismatch; preserve versions and re-register explicitly")
            key = (content_hash, suffix, start, end)
            if key in self._cache:
                total, selected = deepcopy(self._cache[key])
                self._cache.move_to_end(key)
            else:
                if suffix == ".pdf":
                    total, selected = self._pdf_pages(path, start, end)
                else:
                    blocks = _docx_blocks(path)
                    total, selected = len(blocks), blocks[start - 1:end]
                if sum(len(e["text"]) for e in selected) <= MAX_TEXT_CHARS:
                    self._cache[key] = (total, deepcopy(selected))
                    while len(self._cache) > self.max_cache_entries:
                        self._cache.popitem(last=False)
            if _stamp(path) != stamp:
                raise ValueError("Document changed during read; no text result was accepted")
            if start > total or end > total:
                raise ValueError("Requested document range exceeds available pages/text blocks")
            excerpts, remaining, truncated = [], MAX_TEXT_CHARS, False
            empty_units = 0
            for excerpt in selected:
                text = excerpt["text"].strip()
                if not text:
                    empty_units += 1
                    continue
                if remaining <= 0:
                    truncated = True
                    break
                if len(text) > remaining:
                    text, truncated = text[:remaining], True
                excerpts.append({"locator": excerpt["locator"], "text": text, "document_id": document_id,
                                 "source_doi": entry.get("source_doi"), "document_role": entry.get("document_role"),
                                 "source_kind": entry.get("source_kind"), "source_sha256": content_hash})
                remaining -= len(text)
            source_role = entry.get("document_role", "unspecified")
            return {"status": "READ" if excerpts else "UNREADABLE_TEXT", "read": bool(excerpts),
                "access_level": "LOCAL_SOURCE_TEXT_READ" if excerpts else "METADATA_ONLY",
                "document": {k: deepcopy(entry[k]) for k in ("document_id", "title", "source_doi", "document_role", "source_kind") if k in entry},
                "excerpts": excerpts,
                "citable": bool(excerpts) and bool(entry.get("source_doi")) and entry.get("source_kind") in ("publisher", "author")
                           and source_role in ("main_text", "supporting_information", "author_manuscript"),
                "coverage": {"range_unit": "page" if suffix == ".pdf" else "body_text_block", "start": start, "end": end,
                    "document_units": total, "empty_text_units": empty_units, "truncated": truncated,
                    "characters_returned": MAX_TEXT_CHARS - remaining, "full_document_read": False,
                    "full_text_layer_range_read": start == 1 and end == total and not truncated and not empty_units,
                    "images_read": False, "equation_fidelity_verified": False},
                "provenance": {"sha256": content_hash, "registered_path": str(path.relative_to(self.root)),
                               "registry_sha256": hashlib.sha256(json.dumps(self._provided_registry, sort_keys=True).encode()).hexdigest() if self._provided_registry is not None else _sha256(self.registry_path)},
                "permission": {"read": True, "registered_agent_sharing": permissions.get("share_with_agent") is True,
                               "share_with_agent": share_with_agent},
                "boundaries": ["Only the requested text layer was read; figures and scanned content were not interpreted.",
                               "Reading a source is not independent validation of its scientific claims."]}

    @staticmethod
    def agent_projection(result):
        permission = result.get("permission", {})
        if result.get("read") is not True or permission.get("share_with_agent") is not True or permission.get("registered_agent_sharing") is not True:
            raise ValueError("An actual read and explicit registered/per-read sharing grants are required")
        return deepcopy({k: result[k] for k in ("status", "read", "access_level", "document", "excerpts", "citable", "coverage", "provenance", "boundaries")})
