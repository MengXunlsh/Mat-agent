---
name: publication-retrieval
description: Retrieve a specifically identified public paper or ACS supporting-information PDF from a DOI/link or publication identifier into the project.
---

Use `highzyme_retrieve_publication` with a DOI link, bare DOI, `PMC:PMC...` or `MED:PMID`. It reuses mat-agent's exact-identity public retrieval adapters. Network and file-write permissions are required.

`document_id: "article"` saves available article text and the retrieved XML when available. Read `access_level`: an abstract is an abstract, not the full paper. Files include a retrieval manifest and source locations. Use native file tools/literature-evidence to read the saved text.

For ACS SI, request `document_id: "supplements"` using the parent DOI, then select a returned document ID to download its verified PDF. This adapter covers public ACS Figshare SI. For another publisher's explicit public link, use the available native webpage/file retrieval tools, or the user's local file; do not claim the ACS adapter covers it.

Do not repeat downloads if the required source is already saved and suitable. Preserve source files and retrieval metadata. Native web search remains useful for ordinary research questions, but this tool only retrieves an explicitly identified publication.
