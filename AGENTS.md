<!-- BEGIN agent-style v0.3.5 -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
<!-- Adapter: AGENTS.md cross-agent standard -->
<!-- Target path: <repo root>/AGENTS.md -->
<!-- Load class: single-file; install_mode: append-block -->

# agent-style v0.3.5 — AGENTS.md adapter

agent-style is a literature-backed English technical-prose writing ruleset for AI agents. This adapter is the compact rule payload that AGENTS.md-aware tools (Codex, Jules, Zed, Warp, Gemini CLI, VS Code, Aider via `.aider.conf.yml`, and others) load at session start.

## Self-Verification Handshake

When asked "is agent-style active?" or "what writing rules apply here?", answer: `agent-style v0.3.5 active: 21 rules (RULE-01..12 canonical + RULE-A..I field-observed); full bodies at .agent-style/RULES.md.`

## Load Statement

This adapter is loaded as the root `AGENTS.md` file at the repository root. AGENTS.md-aware tools do not auto-import a second file; the compact directives below are what reach context. Full rule bodies at `.agent-style/RULES.md` are a human-readable reference but are not auto-loaded by AGENTS.md consumers.

## The 21 Rules (Compact Directives)

Canonical rules (from Strunk & White 1959, Orwell 1946, Pinker 2014, Gopen & Swan 1990):

- **RULE-01 Curse of knowledge**: Name your intended reader; do not assume they share your tacit knowledge.
- **RULE-02 Passive voice**: Prefer active voice when the agent is known and worth naming.
- **RULE-03 Concrete language**: Prefer concrete, specific terms over abstract category words like "factors" or "aspects".
- **RULE-04 Needless words**: Cut filler phrases like "in order to", "due to the fact that", "may potentially".
- **RULE-05 Dying metaphors**: Delete clichés like "pushes the boundaries", "paradigm shift", or "state of the art".
- **RULE-06 Plain English**: Prefer "use" over "leverage", "method" over "methodology", "feature" over "functionality".
- **RULE-07 Affirmative form**: Prefer "trivial" to "not important", "forgot" to "did not remember".
- **RULE-08 Claim calibration**: Calibrate verbs to evidence; do not write "proves" when the evidence is "suggests".
- **RULE-09 Parallel structure**: Express coordinate ideas in the same grammatical form.
- **RULE-10 Related words together**: Keep subject close to verb and modifier close to modified; split long parentheticals.
- **RULE-11 Stress position**: Place new or important information at the end of the sentence.
- **RULE-12 Long sentences**: Split sentences over 30 words; vary length across a paragraph.

Field-observed rules (maintainer observation of LLM output, 2022-2026):

- **RULE-A Bullet overuse**: Keep prose in paragraphs when ideas connect; bullets only for genuine lists; avoid forced 3-item triads.
- **RULE-B Dash overuse**: Do not use em or en dashes as casual sentence punctuation; prefer commas, semicolons, colons, parentheses.
- **RULE-C Same-starts**: Do not open two or more consecutive sentences with the same word.
- **RULE-D Transitions**: Do not open sentences with "Additionally", "Furthermore", "Moreover", "In addition".
- **RULE-E Summary closers**: Do not end every paragraph with a sentence that restates its point.
- **RULE-F Term consistency**: Once you define a term or abbreviation, keep using it; do not alternate synonyms.
- **RULE-G Title case**: Use title case for section and subsection headings; articles and short prepositions stay lowercase.
- **RULE-H Citation discipline (critical)**: Support factual claims with verifiable citation or concrete evidence; never fabricate citations.
- **RULE-I Contractions**: Prefer "it is" / "does not" / "cannot" over "it's" / "doesn't" / "can't" in formal technical prose.

## Escape Hatch

_"Break any of these rules sooner than say anything outright barbarous."_ — George Orwell, "Politics and the English Language" (1946), Rule 6. Rules are guides to clarity, not ends in themselves.

## Full Rule Bodies (Canonical)

Full directive text, BAD/GOOD example pairs, and rationale per rule: see `.agent-style/RULES.md` in this project, or https://raw.githubusercontent.com/yzhao062/agent-style/v0.3.5/RULES.md for the pinned canonical source.

<!-- END agent-style -->

# Project conventions

## Code style

- Only comment non-obvious code — hidden constraints, subtle invariants, workarounds. If a future reader would not be confused by the comment's absence, leave it out.
- Do not record conversation history, decisions, or task context in comments.
- Keep function and class header comments terse. No more than a paragraph.
- Name identifiers so the code explains itself; rename rather than annotate.
- Follow the "Rule of Three" as a guidepost for factoring out shared logic.
- Break out long functions in to multiple smaller testable units once they exceed a few hundred lines of code. Command entry points can be a bit longer than other functions.
- Emphasis on consistency of patterns across the codebase, except where clarity for other devs would be improved by diverging from a pattern.

### Logging and Exceptions

Every module should get and use its own `logger` for all logging purposes and follow semantic best practices of log levels:

- `debug` logs should be used to record relevant application state at significant logic branches and points of execution. These are not printed to the user unless the `--print debug` option is provided.
- `info` logs are the primary means of showing output to the user, and should be used sparingly/as necessary.
- `warning` logs communicate potential issues with application state or dangerous/unexpected circumstances that do not prevent execution from continuing.
- `error` logs communicate that invalid application or system state was encountered and needs attention, or invalid input was given, and execution cannot continue.
- `critical` logs communicate that an unexpected/unstable state was reached and execution was interrupted.

## Testing

- Cover user-visible behavior and code paths that pose risk to the database or user file system. Skip tests that exist only to raise coverage.
- 100% coverage is not a goal. A passing test for trivial glue code is noise.
- Follow best practices of the "Testing Pyramid". Keep tests isolated to the thing they are testing, and mock away other downstream dependencies.
- Use fixtures to simplify test setup and teardown where it helps.

## Workflow

- Implement the smallest functional slice first, then layer features in follow-up commits. Each commit should be "green" and independently deployable.
- Follow Conventional Commits (see `CONTRIBUTING.md` and the schema in `pyproject.toml`). No `Co-Authored-By` trailer.
- Commit descriptions should be terse and use active tenses (e.g. "add feature")
- Commit bodies are completely optional, and should be used to describe changes when they aren't easily inferred by the main message, they should not include agent conversation context, decisions, or plan notes.
- The agent may commit. But the user always handles pushes, PR creation, and rebases after merges.
- Do not commit spec, brainstorming, or design documents (e.g. anything under `ai-docs/`).
- **Save plans to:** `ai-docs/YYYYMMDD-HHmm-{session-slug}/plan.md` instead of the plugin or skill presets.
- **Save specs to:** `ai-docs/YYYYMMDD-HHmm-{session-slug}/specs.md` instead of the plugin or skill presets.
- **Save decision records to:** `ai-docs/decisions/{topic}.md` (not session-scoped).

## Tooling

- Makefile is used for simple task running: `make test`, `make coverage`, `make lint`, `make format`, `make typecheck` — run before declaring work done.
- `uv` manages dependencies; do not hand-edit `uv.lock`. `uv sync` updates the lockfile.
