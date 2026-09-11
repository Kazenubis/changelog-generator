# Changelog Generator

Parses a repo's git log — written in [Conventional Commits](https://www.conventionalcommits.org/)
format (`type(scope): description`) — into a grouped `CHANGELOG.md`: one
section per release tag, plus a leading "Unreleased" section for
whatever's landed since the last one.

Real output from a sample commit history (2 tagged releases + 1 unreleased commit):

```
# Changelog

## Unreleased

### Bug Fixes

- correct off-by-one in row counter (b6c2149)

## v0.2.0

### BREAKING CHANGES

- **export:** change JSON output to nested product/variant shape (5b91c12)

### Performance Improvements

- cache parsed rows to avoid re-reading the file (9d47094)

### Other Changes

- cleanup old test data (ed2cb28)

## v0.1.0

### Features

- add CSV import for product catalogs (5b2881d)

### Bug Fixes

- **parser:** handle trailing commas in CSV rows (ad2b09a)

### Documentation

- add setup instructions to README (6e4892e)
```

## Features

- Groups commits by release: one `##` section per git tag (newest first),
  plus an `## Unreleased` section for commits since the last tag — or the
  whole history under `Unreleased` if the repo has no tags at all
- Within each release, groups by Conventional Commit type (Features, Bug
  Fixes, Performance, Docs, etc.) in a fixed, sensible reading order
- Breaking changes (`type!:` or `type(scope)!:`) get pulled into their own
  `BREAKING CHANGES` section at the top of their release, impossible to
  miss while skimming
- Commits that don't follow the Conventional Commits format at all aren't
  silently dropped — they land in an `Other Changes` section, so the
  changelog always accounts for every commit
- Built and tested against a real, disposable git repo constructed with
  GitPython in the test suite itself — not a hand-built list of fake
  commit objects standing in for the real thing

## Tech Stack

Python 3 · `GitPython`

## Getting Started

```bash
git clone https://github.com/Kazenubis/changelog-generator.git
cd changelog-generator
pip install -r requirements.txt
python3 changelog_generator.py --repo /path/to/some/git/repo --output CHANGELOG.md
```

Run the tests:

```bash
python3 -m unittest test_changelog_generator.py -v
```

## What I Learned

Deciding where a non-conventional commit message goes mattered more than
I expected. The obvious "just skip it" approach quietly loses real
history — a commit that doesn't happen to follow the format convention
still did something. Routing anything unparseable into an explicit
`Other Changes` section instead means the changelog is always a complete
account of the log, not just the subset that happened to be written in
the right style, and `test_non_conventional_commits_land_in_other_changes_not_dropped`
is there specifically to keep that guarantee from silently regressing.
