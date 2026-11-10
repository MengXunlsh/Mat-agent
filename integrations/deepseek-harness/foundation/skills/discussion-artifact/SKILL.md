---
name: discussion-artifact
description: Turn the selected discussion or existing research results into a reusable note, plan or report while preserving decisions, evidence and source locations.
---

Use the current conversation content or material explicitly supplied by the user. Do not read other conversations' runtime logs. The application's Organize discussion action already selects the source messages, defaults to the latest round, permits up to 15 rounds, and invokes a dedicated editor subagent; retain that flow when initiated from the interface.

Extract the research question, adopted decisions, useful evidence, methods, conditions, results and remaining questions relevant to the requested document. Remove repetition and superseded options. Distinguish proposals from accepted decisions and reported or computed results. Do not conduct new research or calculations merely to fill gaps in a summary.

For direct conversational requests, draft from the available context and use `highzyme_artifact_save` when saving is requested. Do not launch another editor if the application has already delegated this task. Classify the document as source, plan or result, select a meaningful lowercase English filename stem, and write the title and body in the requested language. Use artifact_id for a revision. When the requested deliverable includes data, code or figures, register those output paths in related_files and files with the main document. Cite existing built-in analysis artifacts rather than registering their outputs a second time.

A request to design a new research plan may require other skills and additional work; it is not just summarization. For discussion editing, stop once the requested document is accurate, source-linked and saved or returned as requested.
