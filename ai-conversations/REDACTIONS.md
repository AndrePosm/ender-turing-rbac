# Transcript privacy redactions

`claude-code.jsonl` is a redacted copy of the original native Claude Code session transcript.

- Absolute local project, workspace, home and temporary-directory paths were replaced with explicit `[REDACTED_...]` placeholders. Relative source file names remain readable.
- Configured local credential values and detected authentication tokens or temporary test passwords were replaced with explicit credential placeholders.
- No conversation records were removed, added or reordered. Genuine AI-tool mentions outside filesystem paths were preserved. Modified JSON records were reserialized; their structure and record identifiers were preserved.
- The unmodified native source and a verified private backup remain outside this repository.
- Original browser screenshots, when present, are included in `assets/tool-results/`. Their original local path references in the transcript have privacy placeholders.

Validation: 1384 original records, 1384 retained records; first task reference and implementation commit are present. 12 browser screenshot files are included.
