# Docs Cleanup

`value-cleaner docs` removes documentation that does not help a reader act: READMEs, guides, plans, reports, and reader-facing comments. Scan signals are in brackets.

Apply the [defensive-text removal rule](../SKILL.md#defensive-text-in-rules-and-docs) before judging the remaining candidates below.

## Decision rule

A document earns its place when a reader can act with it faster or more safely than from code, configuration, CI, or another document.

> What can the reader do with this, and where else is it already written?

## Keep

- Verified commands for running, debugging, or reproducing.
- Required environments, services, credentials, fixtures, or data lifecycle.
- Quality gates, ownership, escalation paths, and triage procedures.
- Reasons for boundaries, unusual architecture, or non-obvious decisions.
- Known limitations or gaps with an owner and exit condition.
- Compatibility, regulatory, security, safety, or incident traceability.
- Non-obvious platform differences or scheduling.

## Candidates

### Restated code or configuration

Prose that repeats names, signatures, config values, or package scripts line by line; comments that explain syntax rather than intent; long comments defending brittle code. Remove, or replace with a short reason the behavior matters.

### Duplicate material [duplicate]

Several READMEs repeating the same command with small inconsistencies, or local instructions conflicting with the canonical workflow. Keep one canonical location, preserve unique troubleshooting details, and replace the copies with a link or remove them.

### Obsolete instructions [broken-link, missing-path]

References to removed tools, versions, directories, flags, endpoints, or environment variables; commands that no longer run; architecture the repository no longer uses. Update when the workflow is still relevant; otherwise delete.

### Transient reports and stale status tables [stale-status]

Static coverage percentages, one-time benchmarks, raw output, copied dashboards, and dated pass/fail or status tables with no decision history. Link to the live source or remove them; keep durable thresholds and their rationale.

### Catalogs

Lists of every file, class, or case without risk, ownership, or usage, which need manual updates whenever files move. Delete, or replace with a small map of responsibilities and commands.

### Generic tutorials

Copied documentation for a framework or dependency with no project-specific decision. Delete; link to the official docs when useful.

### Abandoned plans and checklists [todo]

"To add" lists with completed, cancelled, or ownerless items; plans for shipped or removed features; TODOs without owner, date, or criteria. Delete finished material and move active work to the issue tracker.

### Stale matrices and manual scripts

Browser, device, or version matrices nobody runs or owns; steps with no expected result. Convert them to executable checks or a maintained release procedure when they protect real risk; otherwise remove them.

## Examples

### Stacked denials

> The following are fictional writing examples and do not represent real business data.

Once the examples are fictional, the second clause adds nothing. Readers needed neither clause, so the whole sentence was deleted.

### Empty closing summary

After a comparison organized by shared facts and differences:

> The two reports explain who was affected and why it happened.

The sentence restates the comparison above it. Delete it.

## Removing

Compare the text with current code, configuration, CI, and repository structure, and verify commands when execution is available. Do not keep stale documents because they are long or historical; keep incident, compliance, and architectural evidence when retention is required.
