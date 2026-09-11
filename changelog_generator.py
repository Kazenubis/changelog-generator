"""
Changelog Generator — parses a repo's git log (Conventional Commits
format: `type(scope): description`) into a grouped CHANGELOG.md, with one
section per git tag (release) plus a leading "Unreleased" section for
commits since the last tag.
"""

import argparse
import re

import git

CONVENTIONAL_PATTERN = re.compile(
    r"^(?P<type>\w+)(\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<description>.+)$"
)

# Display order; anything not in this list (including unparseable
# commits) falls into "Other Changes" at the end rather than being
# silently dropped.
CATEGORY_ORDER = ["feat", "fix", "perf", "refactor", "docs", "test", "build", "ci", "style", "chore"]
CATEGORY_LABELS = {
    "feat": "Features",
    "fix": "Bug Fixes",
    "perf": "Performance Improvements",
    "refactor": "Code Refactoring",
    "docs": "Documentation",
    "test": "Tests",
    "build": "Build System",
    "ci": "Continuous Integration",
    "style": "Styles",
    "chore": "Chores",
}
OTHER_LABEL = "Other Changes"
BREAKING_LABEL = "BREAKING CHANGES"


def parse_conventional_commit(subject):
    """Parses a commit subject line into {type, scope, breaking,
    description}, or returns None if it doesn't follow the Conventional
    Commits format at all."""
    match = CONVENTIONAL_PATTERN.match(subject.strip())
    if not match:
        return None
    return {
        "type": match.group("type").lower(),
        "scope": match.group("scope"),
        "breaking": bool(match.group("breaking")),
        "description": match.group("description").strip(),
    }


def format_entry(commit):
    """Formats one commit as a changelog bullet line, using its parsed
    Conventional Commit fields when available, or the raw subject
    otherwise."""
    subject = commit.summary
    short_hash = commit.hexsha[:7]
    parsed = parse_conventional_commit(subject)
    if parsed is None:
        return f"{subject} ({short_hash})"
    if parsed["scope"]:
        return f"**{parsed['scope']}:** {parsed['description']} ({short_hash})"
    return f"{parsed['description']} ({short_hash})"


def group_commits_by_type(commits):
    """Returns an ordered dict-like list of (section_label, [entry_line, ...])
    for one version's commits: BREAKING CHANGES first (if any), then each
    Conventional Commit type in CATEGORY_ORDER, then Other Changes last.
    Sections with no commits are omitted entirely."""
    buckets = {label: [] for label in CATEGORY_ORDER}
    breaking = []
    other = []

    for commit in commits:
        parsed = parse_conventional_commit(commit.summary)
        entry = format_entry(commit)
        if parsed is None:
            other.append(entry)
        elif parsed["breaking"]:
            breaking.append(entry)
        elif parsed["type"] in buckets:
            buckets[parsed["type"]].append(entry)
        else:
            other.append(entry)

    sections = []
    if breaking:
        sections.append((BREAKING_LABEL, breaking))
    for key in CATEGORY_ORDER:
        if buckets[key]:
            sections.append((CATEGORY_LABELS[key], buckets[key]))
    if other:
        sections.append((OTHER_LABEL, other))
    return sections


def build_version_groups(repo):
    """Returns [(version_label, [commit, ...]), ...], most recent first:
    an 'Unreleased' group for commits after the latest tag (or the whole
    history if there are no tags at all), then one group per tag, newest
    tag first."""
    tags = sorted(repo.tags, key=lambda t: t.commit.committed_date)
    groups = []

    if tags:
        latest = tags[-1]
        unreleased = list(repo.iter_commits(f"{latest.name}..HEAD"))
    else:
        unreleased = list(repo.iter_commits())
    if unreleased:
        groups.append(("Unreleased", unreleased))

    for i in range(len(tags) - 1, -1, -1):
        tag = tags[i]
        if i == 0:
            commits = list(repo.iter_commits(tag.name))
        else:
            prev = tags[i - 1]
            commits = list(repo.iter_commits(f"{prev.name}..{tag.name}"))
        groups.append((tag.name, commits))

    return groups


def render_changelog(version_groups):
    lines = ["# Changelog", ""]
    for version_label, commits in version_groups:
        lines.append(f"## {version_label}")
        lines.append("")
        for section_label, entries in group_commits_by_type(commits):
            lines.append(f"### {section_label}")
            lines.append("")
            for entry in entries:
                lines.append(f"- {entry}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate_changelog(repo_path, output_path):
    repo = git.Repo(repo_path)
    try:
        version_groups = build_version_groups(repo)
        # render_changelog reads commit.summary/hexsha, which can lazily
        # fetch from the repo's object database — so it has to happen while
        # the repo is still open, not after.
        changelog = render_changelog(version_groups)
    finally:
        # GitPython keeps a persistent `git cat-file` subprocess open on the
        # repo directory once commits have been read (e.g. via iter_commits).
        # On Windows that handle blocks deleting/moving the directory
        # afterward unless the repo is explicitly closed here.
        repo.close()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(changelog)
    return changelog


def main():
    parser = argparse.ArgumentParser(description="Changelog Generator")
    parser.add_argument("--repo", default=".", help="Path to the git repo")
    parser.add_argument("--output", default="CHANGELOG.md")
    args = parser.parse_args()

    changelog = generate_changelog(args.repo, args.output)
    print(changelog)
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
