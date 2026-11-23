"""Unit tests for _format_enum_type helper function.

Task 4.2: Comprehensive unit tests for enum value formatting.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lib.core.get_capabilities.get_capabilities import _format_enum_type

class TestStringValues:
    """Test formatting of string enum values."""

    def test_simple_strings(self):
        result = _format_enum_type(["foo", "bar"])
        assert result == '"foo"|"bar"'

    def test_single_string(self):
        result = _format_enum_type(["only"])
        assert result == '"only"'

    def test_string_with_internal_quotes(self):
        result = _format_enum_type(['say "hello"'])
        assert result == '"say \\"hello\\""'

    def test_string_with_special_characters(self):
        result = _format_enum_type(["a|b", "c&d"])
        assert result == '"a|b"|"c&d"'

    def test_empty_string(self):
        result = _format_enum_type([""])
        assert result == '""'

    def test_many_strings(self):
        values = ["status", "diff", "log", "add", "commit", "push",
                  "pull", "merge", "rebase", "checkout", "branch",
                  "stash", "blame", "init"]
        result = _format_enum_type(values)
        assert result == '"status"|"diff"|"log"|"add"|"commit"|"push"|"pull"|"merge"|"rebase"|"checkout"|"branch"|"stash"|"blame"|"init"'

class TestIntegerValues:
    """Test formatting of integer enum values."""

    def test_simple_integers(self):
        result = _format_enum_type([1, 2, 3])
        assert result == "1|2|3"

    def test_single_integer(self):
        result = _format_enum_type([42])
        assert result == "42"

    def test_negative_integers(self):
        result = _format_enum_type([-1, 0, 1])
        assert result == "-1|0|1"

    def test_zero(self):
        result = _format_enum_type([0])
        assert result == "0"

class TestBooleanValues:
    """Test formatting of boolean enum values."""

    def test_true_and_false(self):
        result = _format_enum_type([True, False])
        assert result == "true|false"

    def test_only_true(self):
        result = _format_enum_type([True])
        assert result == "true"

    def test_only_false(self):
        result = _format_enum_type([False])
        assert result == "false"

    def test_bool_not_treated_as_int(self):
        """Bool subclasses int in Python; must format as true/false not 1/0."""
        result = _format_enum_type([True, False])
        assert "true" in result
        assert "false" in result
        assert "1" not in result
        assert "0" not in result

class TestFloatValues:
    """Test formatting of float enum values."""

    def test_simple_floats(self):
        result = _format_enum_type([1.5, 2.5])
        assert result == "1.5|2.5"

    def test_whole_number_float(self):
        result = _format_enum_type([1.0])
        assert result == "1.0"

class TestMixedTypes:
    """Test formatting of mixed-type enum values."""

    def test_string_and_integer(self):
        result = _format_enum_type(["foo", 1])
        assert result == '"foo"|1'

    def test_string_integer_bool(self):
        result = _format_enum_type(["foo", 1, True])
        assert result == '"foo"|1|true'

    def test_bool_before_int_ordering(self):
        """Confirm bool check runs before int since bool is subclass of int."""
        result = _format_enum_type([True, 1, False, 0])
        # True -> true, 1 -> 1, False -> false, 0 -> 0
        assert result == "true|1|false|0"

class TestEdgeCases:
    """Test edge cases."""

    def test_empty_list(self):
        result = _format_enum_type([])
        assert result == ""

    def test_pipe_separator_count(self):
        """N values should have N-1 pipe separators."""
        result = _format_enum_type(["a", "b", "c"])
        assert result.count("|") == 2

    def test_output_starts_and_ends_correctly(self):
        result = _format_enum_type(["foo", "bar"])
        assert not result.startswith("|")
        assert not result.endswith("|")
