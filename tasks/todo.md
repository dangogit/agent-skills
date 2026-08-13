# Publish invoice-pack (2026-08-13)

## Plan

- [x] Bootstrap the public `agent-skills` repository and `invoice-pack` skill.
- [x] Implement local document indexing, Israeli card-statement parsing,
      conservative matching, deduplication, and report generation.
- [x] Document Gmail/Apple Mail collection and privacy-safe operation.
- [x] Test with fully synthetic Hebrew and international invoice data.
- [x] Validate the skill, review the full diff, and prepare the release PR.

## Review

Created a dependency-free local pack builder with Hebrew/English CSV and XLSX
header detection, PDF/text/HTML/EML indexing, SHA-256 deduplication, original-
currency matching, one-document-per-transaction enforcement, and fail-closed
review handling. It emits a linked RTL HTML report, UTF-8 CSV, privacy-safe JSON
manifest, matched files, review candidates, unmatched files, and a missing list.

Seven synthetic tests pass on Python 3.9 and 3.12, including foreign-currency
matching, ambiguous candidates, duplicate documents, Hebrew XLSX, HTML escaping,
email-only mode, and refusal to auto-match an image without OCR. The public demo
produces two matches and one missing invoice. The skill validator, Python compile,
`git diff --check`, rendered RTL report inspection, and Snyk Code High scan pass.
GitHub Actions also passes on Python 3.9 and 3.12 after validating the workflow
syntax and the exact PR branch.

# Publish hebrew-keyboard-mistype (2026-08-13)

## Plan

- [x] Package the existing decoder as a self-contained public skill.
- [x] Correct the documented keyboard-layout examples.
- [x] Add deterministic decoder and Claude Code hook tests.
- [x] Update repository discovery and installation documentation.
- [x] Validate, review, and prepare the release PR.

## Review

The skill is local-only and dependency-free beyond Python. Four public examples
round-trip through the same deterministic mapping used at runtime. Six focused
tests cover examples, mixed input, standard input, hook output, silent prompts,
and malformed hook payloads. The suite passes on Python 3.9 and 3.12, the
official validator passes, the dual-axis review scores 97/100, and Snyk Code
reports zero high-severity issues.
