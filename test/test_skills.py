"""Module documentation."""

import os
import tempfile
import unittest
from pathlib import Path
from typing import get_args, get_type_hints
from unittest import mock

from lib.core import skills


class FakeMCP:
    """FakeMCP class."""

    def __init__(self) -> None:
        """Init function."""
        self.descriptions = {}

    def tool(self, description):
        """Tool function."""

        def register(function):
            """Register function."""
            self.descriptions[function.__name__] = description
            return function

        return register


class SkillsToolTests(unittest.TestCase):
    """SkillsToolTests class."""

    def setUp(self) -> None:
        """SetUp function."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "skills"
        patcher = mock.patch.dict(os.environ, {skills.SKILLS_DIR_ENV: str(self.dir)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def save(self, name="my-skill", **overrides):
        """Save function."""
        args: dict = {
            "action": "save",
            "name": name,
            "description": "Does a thing.",
            "content": "Step one.\nStep two.",
        }
        args.update(overrides)
        return skills.skills_manage(**args)

    def test_list_on_missing_directory_is_empty(self) -> None:
        """Test list on missing directory is empty function."""
        result = skills.skills_manage(action="list")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["skills"], [])

    def test_save_then_get_round_trip(self) -> None:
        """Test save then get round trip function."""
        saved = self.save()
        self.assertTrue(saved["saved"])
        self.assertTrue(saved["created"])
        got = skills.skills_manage(action="get", name="my-skill")
        self.assertEqual(got["name"], "my-skill")
        self.assertEqual(got["description"], "Does a thing.")
        self.assertTrue(got["invokable"])
        self.assertEqual(got["body"].strip(), "Step one.\nStep two.")
        self.assertTrue(got["content"].startswith("---\nname: my-skill\n"))
        self.assertTrue((self.dir / "my-skill" / "SKILL.md").is_file())

    def test_list_returns_sorted_entries(self) -> None:
        """Test list returns sorted entries function."""
        self.save("b-skill", description="Second.")
        self.save("a-skill", description="First.", invokable=False)
        result = skills.skills_manage(action="list")
        self.assertEqual([s["name"] for s in result["skills"]], ["a-skill", "b-skill"])
        self.assertFalse(result["skills"][0]["invokable"])
        self.assertEqual(result["skills"][1]["description"], "Second.")

    def test_list_query_ranks_metadata_matches_and_limits_results(self) -> None:
        for name in ["e-match", "d-match", "c-match", "b-match", "a-match", "z-match"]:
            self.save(name, description="testing helper", tags=["unit"])
        self.save("top-match", description="python testing task", tags=["python"])
        result = skills.skills_manage(action="list", query="python testing")
        self.assertEqual(result["count"], 5)
        self.assertEqual(
            [skill["name"] for skill in result["skills"]],
            ["top-match", "a-match", "b-match", "c-match", "d-match"],
        )

    def test_list_query_returns_empty_for_unmatched_query(self) -> None:
        self.save()
        result = skills.skills_manage(action="list", query="unmatched zebra")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["skills"], [])

    def test_search_remains_substring_filter(self) -> None:
        self.save("first", description="Python helper")
        self.save("second", description="Java helper")
        result = skills.skills_manage(action="search", query="python")
        self.assertEqual([skill["name"] for skill in result["skills"]], ["first"])

    def test_save_refuses_overwrite_by_default(self) -> None:
        """Test save refuses overwrite by default function."""
        self.save()
        again = self.save(content="Different.")
        self.assertEqual(again["error_code"], "already_exists")
        got = skills.skills_manage(action="get", name="my-skill")
        self.assertIn("Step one.", got["body"])

    def test_save_with_overwrite_replaces(self) -> None:
        """Test save with overwrite replaces function."""
        self.save()
        again = self.save(content="Different.", overwrite=True)
        self.assertTrue(again["saved"])
        self.assertFalse(again["created"])
        got = skills.skills_manage(action="get", name="my-skill")
        self.assertEqual(got["body"].strip(), "Different.")
        leftovers: list = [p.name for p in self.dir.rglob("*.tmp")]
        self.assertEqual(leftovers, [])

    def test_invalid_names_are_rejected_and_write_nothing(self) -> None:
        """Test invalid names are rejected and write nothing function."""
        outside = Path(self._tmp.name) / "escaped.md"
        for bad in [
            "../escaped",
            "a/b",
            "A-Upper",
            "-lead",
            "",
            "x" * 65,
            "dot.name",
            "..\\evil",
        ]:
            with self.subTest(name=bad):
                result = self.save(bad)
                self.assertIn(
                    result["error_code"], {"invalid_name", "missing_argument"}
                )
                result = skills.skills_manage(action="get", name=bad)
                self.assertIn(
                    result["error_code"], {"invalid_name", "missing_argument"}
                )
        self.assertFalse(outside.exists())
        self.assertFalse(self.dir.exists() and any(self.dir.iterdir()))

    def test_get_unknown_skill(self) -> None:
        """Test get unknown skill function."""
        result = skills.skills_manage(action="get", name="nope")
        self.assertEqual(result["error_code"], "not_found")

    def test_get_requires_name(self) -> None:
        """Test get requires name function."""
        result = skills.skills_manage(action="get")
        self.assertEqual(result["error_code"], "missing_argument")

    def test_save_requires_description_and_content(self) -> None:
        """Test save requires description and content function."""
        self.assertEqual(self.save(description=None)["error_code"], "missing_argument")
        self.assertEqual(self.save(description="  ")["error_code"], "missing_argument")
        self.assertEqual(self.save(content=None)["error_code"], "missing_argument")
        self.assertEqual(self.save(content="\n ")["error_code"], "missing_argument")

    def test_description_must_be_single_short_line(self) -> None:
        """Test description must be single short line function."""
        self.assertEqual(
            self.save(description="a\nb")["error_code"], "invalid_description"
        )
        self.assertEqual(
            self.save(description="x" * 301)["error_code"], "invalid_description"
        )

    def test_content_with_frontmatter_is_rejected(self) -> None:
        """Test content with frontmatter is rejected function."""
        result = self.save(content="---\nname: x\n---\nbody")
        self.assertEqual(result["error_code"], "content_has_frontmatter")

    def test_oversized_skill_is_rejected(self) -> None:
        """Test oversized skill is rejected function."""
        result = self.save(content="x" * (skills.MAX_SKILL_BYTES + 1))
        self.assertEqual(result["error_code"], "skill_too_large")

    def test_crlf_frontmatter_is_parsed(self) -> None:
        """Test crlf frontmatter is parsed function."""
        self.dir.mkdir(parents=True)
        (self.dir / "win").mkdir(parents=True)
        (self.dir / "win" / "SKILL.md").write_bytes(
            b"---\r\nname: win\r\ndescription: From Windows.\r\ninvokable: false\r\n---\r\n\r\nBody\r\n"
        )
        got = skills.skills_manage(action="get", name="win")
        self.assertEqual(got["description"], "From Windows.")
        self.assertFalse(got["invokable"])
        self.assertEqual(got["body"].strip(), "Body")

    def test_binary_skill_file_is_reported_not_raised(self) -> None:
        """Test binary skill file is reported not raised function."""
        self.dir.mkdir(parents=True)
        (self.dir / "bad").mkdir(parents=True)
        (self.dir / "bad" / "SKILL.md").write_bytes(b"\xff\xfe\x00bad")
        listed = skills.skills_manage(action="list")
        self.assertEqual(listed["errors"][0]["error_code"], "binary_file")
        got = skills.skills_manage(action="get", name="bad")
        self.assertEqual(got["error_code"], "binary_file")


    def test_list_references_returns_sorted_markdown_entries(self) -> None:
        """Test list references returns sorted markdown entries function."""
        self.save(name="ref-skill")
        ref_dir = self.dir / "ref-skill" / "references"
        ref_dir.mkdir(parents=True)
        (ref_dir / "zeta.md").write_text("# Zeta\n")
        (ref_dir / "alpha.md").write_text("# Alpha\n")
        (ref_dir / "ignore.txt").write_text("skip\n")
        result = skills.skills_manage(action="list_references", name="ref-skill")
        self.assertEqual(result["name"], "ref-skill")
        self.assertEqual(result["count"], 2)
        self.assertEqual(
            [item["name"] for item in result["references"]], ["alpha", "zeta"]
        )

    def test_get_reference_returns_content(self) -> None:
        """Test get reference returns content function."""
        self.save(name="ref-skill")
        ref_dir = self.dir / "ref-skill" / "references"
        ref_dir.mkdir(parents=True)
        (ref_dir / "overview.md").write_text("# Overview\nLine two\n")
        result = skills.skills_manage(
            action="get_reference", name="ref-skill", reference="overview"
        )
        self.assertEqual(result["name"], "ref-skill")
        self.assertEqual(result["reference"], "overview")
        self.assertEqual(result["file"], "overview.md")
        self.assertIn("Line two", result["content"])

    def test_reference_actions_validate_inputs_and_missing_files(self) -> None:
        """Test reference actions validate inputs and missing files function."""
        self.save(name="ref-skill")
        self.assertEqual(
            skills.skills_manage(action="list_references")["error_code"],
            "missing_argument",
        )
        self.assertEqual(
            skills.skills_manage(
                action="get_reference", name="ref-skill", reference="bad.name"
            )["error_code"],
            "invalid_reference_name",
        )
        self.assertEqual(
            skills.skills_manage(
                action="get_reference", name="ref-skill", reference="missing"
            )["error_code"],
            "not_found",
        )
        self.assertEqual(
            skills.skills_manage(action="list_references", name="unknown")["error_code"],
            "not_found",
        )


class BaselineSkillsTests(unittest.TestCase):
    """Run against the real project skills directory (read-only)."""

    def test_register_description_omits_skill_catalog(self) -> None:
        """Test register description omits skill catalog function."""
        mcp = FakeMCP()
        skills.register(mcp)
        description = mcp.descriptions["skills_manage"]
        self.assertNotIn("Default baseline skills and descriptions", description)
        self.assertNotIn("Installed skills and their descriptions", description)
        self.assertNotIn("- plan:", description)
        self.assertNotIn("- troubleshoot:", description)

    def test_action_argument_describes_query_based_list(self) -> None:
        """Test action argument describes query based list function."""
        action_hint = get_type_hints(skills.skills_manage, include_extras=True)[
            "action"
        ]
        action_field = get_args(action_hint)[1]
        self.assertIn("query is supplied", action_field.description)

    def test_baseline_skills_are_listed(self) -> None:
        """Test baseline skills are listed function."""
        with mock.patch.dict(os.environ):
            os.environ.pop(skills.SKILLS_DIR_ENV, None)
            result = skills.skills_manage(action="list")
            names: set = {s["name"] for s in result["skills"]}
            self.assertTrue({"grill-me", "handoff"} <= names)
            got = skills.skills_manage(action="get", name="handoff")
            self.assertIn("handoff", got["description"].lower())


if __name__ == "__main__":
    unittest.main()
