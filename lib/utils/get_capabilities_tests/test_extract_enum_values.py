"""Unit tests for _extract_enum_values helper function."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lib.workspace_context.get_capabilities.get_capabilities import _extract_enum_values


def test_enum_field_pattern():
    """Test Pattern 1: enum field with values."""
    definition = {"enum": ["foo", "bar", "baz"], "type": "string"}
    result = _extract_enum_values(definition)
    assert result == ["foo", "bar", "baz"], f"Expected ['foo', 'bar', 'baz'], got {result}"
    print("✓ Test enum field pattern passed")


def test_anyof_with_const_pattern():
    """Test Pattern 2: anyOf with const values."""
    definition = {
        "anyOf": [
            {"const": "read", "type": "string"},
            {"const": "write", "type": "string"},
            {"const": "append", "type": "string"}
        ]
    }
    result = _extract_enum_values(definition)
    assert result == ["read", "write", "append"], f"Expected ['read', 'write', 'append'], got {result}"
    print("✓ Test anyOf with const pattern passed")


def test_integer_enum():
    """Test enum field with integer values."""
    definition = {"enum": [1, 2, 3, 4, 5], "type": "integer"}
    result = _extract_enum_values(definition)
    assert result == [1, 2, 3, 4, 5], f"Expected [1, 2, 3, 4, 5], got {result}"
    print("✓ Test integer enum passed")


def test_mixed_enum():
    """Test enum field with mixed types."""
    definition = {"enum": ["foo", 1, True]}
    result = _extract_enum_values(definition)
    assert result == ["foo", 1, True], f"Expected ['foo', 1, True], got {result}"
    print("✓ Test mixed enum passed")


def test_no_enum_returns_none():
    """Test that non-enum definitions return None."""
    definition = {"type": "string"}
    result = _extract_enum_values(definition)
    assert result is None, f"Expected None, got {result}"
    print("✓ Test no enum returns None passed")


def test_empty_enum_returns_none():
    """Test that empty enum list returns None."""
    definition = {"enum": [], "type": "string"}
    result = _extract_enum_values(definition)
    assert result is None, f"Expected None for empty enum, got {result}"
    print("✓ Test empty enum returns None passed")


def test_malformed_anyof_returns_none():
    """Test that anyOf without const in all items returns None."""
    definition = {
        "anyOf": [
            {"const": "foo"},
            {"type": "string"}  # Missing const
        ]
    }
    result = _extract_enum_values(definition)
    assert result is None, f"Expected None for malformed anyOf, got {result}"
    print("✓ Test malformed anyOf returns None passed")


def test_anyof_not_list_returns_none():
    """Test that anyOf that's not a list returns None."""
    definition = {"anyOf": "not a list"}
    result = _extract_enum_values(definition)
    assert result is None, f"Expected None for non-list anyOf, got {result}"
    print("✓ Test anyOf not list returns None passed")


def test_enum_not_list_returns_none():
    """Test that enum that's not a list returns None."""
    definition = {"enum": "not a list"}
    result = _extract_enum_values(definition)
    assert result is None, f"Expected None for non-list enum, got {result}"
    print("✓ Test enum not list returns None passed")


if __name__ == "__main__":
    print("Running _extract_enum_values unit tests...\n")
    
    test_enum_field_pattern()
    test_anyof_with_const_pattern()
    test_integer_enum()
    test_mixed_enum()
    test_no_enum_returns_none()
    test_empty_enum_returns_none()
    test_malformed_anyof_returns_none()
    test_anyof_not_list_returns_none()
    test_enum_not_list_returns_none()
    
    print("\n✅ All tests passed!")
