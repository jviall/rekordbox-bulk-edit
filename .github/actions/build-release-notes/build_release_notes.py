#!/usr/bin/env python3
"""Build categorized release notes from commits, linking each commit's PR.

Lists one entry per commit (not per PR) between ``FROM_TAG`` (exclusive) and
``TO_TAG`` (inclusive). Each entry links the pull request that introduced the
commit and credits its author. The PR (number and author login) is resolved via
``GET /repos/{repo}/commits/{sha}/pulls``, which works for both squash and
rebase merges. Commits with no associated PR fall back to a short-SHA reference
and the git author name.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

# Category matchers, evaluated in order; first match wins. Mirrors the
# conventional-commit types accepted by the project's commitizen schema.
_BREAKING_TITLE = re.compile(r"^(BREAKING(\(.*\))?:|(\w+)?(\(.*\))?!:)")
_BREAKING_BODY = re.compile(r"BREAKING[\- ]CHANGE")
_CATEGORY_TITLE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("## Features", re.compile(r"^feat(\(.*\))?:")),
    ("## Fixes", re.compile(r"^fix(?!\(deps\))(\(.*\))?:")),
    (
        "## Chores",
        re.compile(
            r"^(chore(?!\(deps\))|refactor|ci|docs|style|perf|test|build)(\(.*\))?:"
        ),
    ),
    ("## Dependency Updates", re.compile(r"^(chore|fix)\(deps\):")),
]
_BREAKING_TITLE_HEADER = "## Breaking Changes"
_UNCATEGORIZED_HEADER = "## Uncategorized"
_CATEGORY_ORDER = [
    _BREAKING_TITLE_HEADER,
    "## Features",
    "## Fixes",
    "## Chores",
    "## Dependency Updates",
    _UNCATEGORIZED_HEADER,
]

# Commits that are noise in a changelog: merge commits are dropped at the
# ``git log`` level (--no-merges); version-bump commits are filtered here.
_SKIP_SUBJECT = re.compile(r"^bump:")
# A trailing "(#NN)" left by squash merges, stripped so it is not duplicated
# alongside the resolved reference.
_TRAILING_PR = re.compile(r"\s*\(#\d+\)\s*$")

_RECORD_SEP = "\x1e"
_FIELD_SEP = "\x1f"


@dataclass
class Commit:
    sha: str
    subject: str
    body: str
    author: str


@dataclass
class Category:
    header: str
    lines: list[str] = field(default_factory=list)


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8")


def read_commits(from_tag: str, to_tag: str) -> list[Commit]:
    rng = f"{from_tag}..{to_tag}" if from_tag else to_tag
    fmt = _FIELD_SEP.join(["%H", "%s", "%b", "%an"]) + _RECORD_SEP
    result = _run(["git", "log", "--no-merges", f"--format={fmt}", rng])
    if result.returncode != 0:
        raise SystemExit(f"git log failed for range '{rng}': {result.stderr.strip()}")

    commits: list[Commit] = []
    for record in result.stdout.split(_RECORD_SEP):
        record = record.strip("\n")
        if not record:
            continue
        sha, subject, body, author = (record.split(_FIELD_SEP) + ["", "", ""])[:4]
        commits.append(
            Commit(
                sha=sha,
                subject=subject.strip(),
                body=body.strip(),
                author=author.strip(),
            )
        )
    return commits


def resolve_pr(repo: str, sha: str) -> tuple[int, str] | None:
    """Return the (number, author_login) of a commit's PR, or None if unresolved."""
    result = _run(["gh", "api", f"repos/{repo}/commits/{sha}/pulls"])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    merged = [pr for pr in prs if pr.get("merged_at")]
    chosen = merged[0] if merged else (prs[0] if prs else None)
    if not chosen:
        return None
    login = (chosen.get("user") or {}).get("login", "")
    return chosen["number"], login


def categorize(commit: Commit) -> str:
    if _BREAKING_TITLE.match(commit.subject) or _BREAKING_BODY.search(commit.body):
        return _BREAKING_TITLE_HEADER
    for header, pattern in _CATEGORY_TITLE_RULES:
        if pattern.match(commit.subject):
            return header
    return _UNCATEGORIZED_HEADER


def render_line(commit: Commit, repo: str) -> str:
    subject = _TRAILING_PR.sub("", commit.subject)
    pr = resolve_pr(repo, commit.sha)
    if pr is not None:
        number, login = pr
        credit = f"#{number} by @{login}" if login else f"#{number}"
        return f"- {subject} ({credit})"
    return f"- {subject} ({commit.sha[:7]} by {commit.author})"


def build_notes(commits: list[Commit], repo: str) -> str:
    categories = {header: Category(header) for header in _CATEGORY_ORDER}
    for commit in commits:
        if _SKIP_SUBJECT.match(commit.subject):
            continue
        categories[categorize(commit)].lines.append(render_line(commit, repo))

    sections = [
        f"{cat.header}\n" + "\n".join(cat.lines)
        for header in _CATEGORY_ORDER
        if (cat := categories[header]).lines
    ]
    return "\n\n".join(sections) if sections else "_No changes._"


def main() -> None:
    to_tag = os.environ.get("TO_TAG", "").strip()
    if not to_tag:
        raise SystemExit("TO_TAG is required")
    from_tag = os.environ.get("FROM_TAG", "").strip()
    repo = os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        raise SystemExit("REPO (or GITHUB_REPOSITORY) is required")
    output_file = os.environ.get("OUTPUT_FILE", "release-notes.md")

    commits = read_commits(from_tag, to_tag)
    notes = build_notes(commits, repo)
    with open(output_file, "w", encoding="utf-8") as handle:
        handle.write(notes + "\n")
    print(notes, file=sys.stderr)


if __name__ == "__main__":
    main()
