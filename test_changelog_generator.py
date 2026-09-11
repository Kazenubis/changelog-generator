import tempfile
import unittest

import git

from changelog_generator import (
    build_version_groups,
    generate_changelog,
    group_commits_by_type,
    parse_conventional_commit,
    render_changelog,
)


def make_repo_with_commits(tmpdir):
    """Builds a real git repo with a small, deliberately mixed commit
    history: conventional and non-conventional messages, a scoped commit,
    a breaking change, and one tag splitting 'released' from 'unreleased'
    work — so the grouping logic runs against an actual git log, not a
    hand-built list of fake commit objects."""
    repo = git.Repo.init(tmpdir)
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.com")

    def commit(message, filename):
        path = f"{tmpdir}/{filename}"
        with open(path, "w") as f:
            f.write(message)
        repo.index.add([path])
        return repo.index.commit(message)

    commit("feat: add login page", "f1.txt")
    commit("fix(auth): correct token expiry check", "f2.txt")
    commit("chore: update dependencies", "f3.txt")
    repo.create_tag("v1.0.0")

    commit("feat(api)!: rename /users endpoint to /accounts", "f4.txt")
    commit("just tweak some stuff", "f5.txt")  # non-conventional
    commit("docs: add API usage examples", "f6.txt")

    return repo


class TestParseConventionalCommit(unittest.TestCase):
    def test_parses_simple_type_and_description(self):
        result = parse_conventional_commit("feat: add login page")
        self.assertEqual(result["type"], "feat")
        self.assertIsNone(result["scope"])
        self.assertFalse(result["breaking"])
        self.assertEqual(result["description"], "add login page")

    def test_parses_scope(self):
        result = parse_conventional_commit("fix(auth): correct token expiry check")
        self.assertEqual(result["type"], "fix")
        self.assertEqual(result["scope"], "auth")

    def test_parses_breaking_marker(self):
        result = parse_conventional_commit("feat(api)!: rename endpoint")
        self.assertTrue(result["breaking"])

    def test_non_conventional_message_returns_none(self):
        self.assertIsNone(parse_conventional_commit("just tweak some stuff"))


class TestGroupCommitsByType(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo = make_repo_with_commits(self.tmpdir.name)

    def tearDown(self):
        # Windows keeps GitPython's cat-file subprocess handle open on the
        # repo directory until the Repo is explicitly closed; without this,
        # tmpdir.cleanup() fails with PermissionError on Windows only.
        self.repo.close()
        self.tmpdir.cleanup()

    def test_breaking_changes_get_their_own_section_first(self):
        unreleased_commits = list(self.repo.iter_commits("v1.0.0..HEAD"))
        sections = group_commits_by_type(unreleased_commits)
        self.assertEqual(sections[0][0], "BREAKING CHANGES")
        self.assertIn("rename /users endpoint to /accounts", sections[0][1][0])

    def test_non_conventional_commits_land_in_other_changes_not_dropped(self):
        unreleased_commits = list(self.repo.iter_commits("v1.0.0..HEAD"))
        sections = dict(group_commits_by_type(unreleased_commits))
        self.assertIn("Other Changes", sections)
        self.assertTrue(any("just tweak some stuff" in e for e in sections["Other Changes"]))

    def test_empty_sections_are_omitted(self):
        released_commits = list(self.repo.iter_commits("v1.0.0"))
        sections = dict(group_commits_by_type(released_commits))
        # No perf/refactor/test/build/ci/style commits in this history.
        self.assertNotIn("Performance Improvements", sections)
        self.assertNotIn("Tests", sections)


class TestVersionGroups(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo = make_repo_with_commits(self.tmpdir.name)

    def tearDown(self):
        # See TestGroupCommitsByType.tearDown: Repo.close() is required
        # before cleanup() on Windows.
        self.repo.close()
        self.tmpdir.cleanup()

    def test_unreleased_group_comes_first_and_excludes_tagged_commits(self):
        groups = build_version_groups(self.repo)
        labels = [label for label, _commits in groups]
        self.assertEqual(labels, ["Unreleased", "v1.0.0"])

    def test_each_group_has_the_correct_commit_count(self):
        groups = dict(build_version_groups(self.repo))
        self.assertEqual(len(groups["Unreleased"]), 3)
        self.assertEqual(len(groups["v1.0.0"]), 3)

    def test_no_tags_at_all_puts_everything_under_unreleased(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = git.Repo.init(tmp)
            with repo.config_writer() as config:
                config.set_value("user", "name", "Test User")
                config.set_value("user", "email", "test@example.com")
            path = f"{tmp}/f.txt"
            open(path, "w").close()
            repo.index.add([path])
            repo.index.commit("feat: first commit")

            groups = build_version_groups(repo)
            repo.close()  # release the cat-file handle before the tmpdir is removed (Windows)
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0][0], "Unreleased")


class TestRenderAndGenerate(unittest.TestCase):
    def test_render_changelog_produces_expected_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo_with_commits(tmp)
            groups = build_version_groups(repo)
            # render_changelog reads commit.summary/hexsha lazily, so it has
            # to run before repo.close(), not after.
            changelog = render_changelog(groups)
            repo.close()  # release the cat-file handle before the tmpdir is removed (Windows)
            self.assertIn("# Changelog", changelog)
            self.assertIn("## Unreleased", changelog)
            self.assertIn("## v1.0.0", changelog)
            self.assertIn("### BREAKING CHANGES", changelog)
            self.assertIn("### Bug Fixes", changelog)

    def test_generate_changelog_writes_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo_with_commits(tmp)
            output_path = f"{tmp}/CHANGELOG.md"
            changelog = generate_changelog(tmp, output_path)
            with open(output_path) as f:
                written = f.read()
            self.assertEqual(changelog, written)


if __name__ == "__main__":
    unittest.main()
