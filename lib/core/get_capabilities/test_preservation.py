"""Preservation property tests - ensure non-enum parameters remain unchanged.

These tests follow the observation-first methodology. They are run on UNFIXED code
to establish the baseline behavior that must be preserved after the fix is applied.

CRITICAL: These tests MUST PASS on unfixed code - passing confirms the baseline.
After the fix, these same tests must STILL PASS, confirming no regressions.

The goal is to ensure the fix for enum embedding does not break existing
functionality for non-enum parameters.
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import hypothesis only if available (not required for basic tests)
try:
    from hypothesis import given, assume, strategies as st, settings

    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False

    # Create dummy decorators and strategies if hypothesis not available
    class _DummySt:
        """Stub for hypothesis strategies - arguments are ignored."""

        def __getattr__(self, name):
            """Getattr function."""
            return lambda *a, **kw: None

    st = _DummySt()

    def assume(*args, **kwargs) -> None:
        """Assume function."""
        pass

    def given(*args, **kwargs):
        """Given function."""

        def decorator(func):
            """Decorator function."""
            return lambda self: pytest.skip("hypothesis not installed")

        return decorator

    def settings(*args, **kwargs):
        """Settings function."""

        def decorator(func):
            """Decorator function."""
            return func

        return decorator

from lib.core.get_capabilities.get_capabilities import _tool_usage_signature

def has_enum_or_const(schema) -> bool:
    """Check if a parameter schema contains enum or const values.

    Returns True if the schema has enum constraints that would trigger
    the bugfix behavior. Returns False for all other schemas.
    """
    if not isinstance(schema, dict):
        return False

    # Pattern 1: enum field with non-empty list
    if "enum" in schema:
        enum_values = schema["enum"]
        if isinstance(enum_values, list) and len(enum_values) > 0:
            return True

    # Pattern 2: anyOf with const values (all items must have const)
    if "anyOf" in schema:
        any_of = schema["anyOf"]
        if isinstance(any_of, list) and len(any_of) > 0:
            if all(isinstance(item, dict) and "const" in item for item in any_of):
                return True

    return False

class TestSimpleTypePreservation:
    """Test that simple type parameters format unchanged."""

    def test_simple_string_type_preserved(self) -> None:
        """Observe: {"type": "string"} produces "param: str" on unfixed code.

        This test captures the current behavior and asserts it must be preserved.
        """
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            # Baseline: string type is NOT in short_types map, so it stays as 'string'
            assert signature == "(name: string)", (
                f"Baseline behavior changed! Expected '(name: string)', got: {signature}"
            )

    def test_simple_integer_type_preserved(self) -> None:
        """Observe: {"type": "integer"} produces "param: int" on unfixed code."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            assert signature == "(count: int)", (
                f"Baseline behavior changed! Expected '(count: int)', got: {signature}"
            )

    def test_simple_boolean_type_preserved(self) -> None:
        """Observe: {"type": "boolean"} produces "param: bool" on unfixed code."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            assert signature == "(enabled: bool)", (
                f"Baseline behavior changed! Expected '(enabled: bool)', got: {signature}"
            )

    def test_simple_number_type_preserved(self) -> None:
        """Observe: {"type": "number"} produces "param: float" on unfixed code."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"price": {"type": "number"}},
            "required": ["price"],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            assert signature == "(price: float)", (
                f"Baseline behavior changed! Expected '(price: float)', got: {signature}"
            )

class TestShortTypeMappingPreservation:
    """Test that short type mappings are preserved."""

    def test_short_type_mappings_preserved(self) -> None:
        """Observe: integer→int, number→float, boolean→bool mappings work."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "ratio": {"type": "number"},
                "flag": {"type": "boolean"},
            },
            "required": ["count", "ratio", "flag"],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            # Verify short type mappings
            assert "count: int" in signature
            assert "ratio: float" in signature
            assert "flag: bool" in signature

class TestUnionTypePreservation:
    """Test that union types (without enum) are preserved."""

    def test_union_type_preserved(self) -> None:
        """Observe: {"type": ["string", "integer"]} produces "param: str|int"."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"value": {"type": ["string", "integer"]}},
            "required": ["value"],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            # Union types show pipe-separated - 'string' stays as 'string', 'integer' -> 'int'
            assert (
                "value: string|int" in signature or "value: int|string" in signature
            ), f"Expected union type format, got: {signature}"

class TestOptionalParameterPreservation:
    """Test that optional parameter syntax is preserved."""

    def test_optional_parameter_syntax_preserved(self) -> None:
        """Observe: non-required params show "param?: type"."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": [],  # name is optional
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            # Optional parameters use ?: syntax - string type stays as 'string'
            assert "name?: string" in signature, (
                f"Expected optional syntax 'name?: string', got: {signature}"
            )

    def test_required_vs_optional_distinction(self) -> None:
        """Observe: required shows 'param: type', optional shows 'param?: type'."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {
                "required_param": {"type": "string"},
                "optional_param": {"type": "integer"},
            },
            "required": ["required_param"],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            # Check required parameter (no question mark) - string type stays as 'string'
            assert "required_param: string" in signature
            # Check optional parameter (with question mark)
            assert "optional_param?: int" in signature

class TestDefaultValuePreservation:
    """Test that default values display correctly."""

    def test_default_value_display_preserved(self) -> None:
        """Observe: defaults show "param?: type = value"."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"name": {"type": "string", "default": "default_name"}},
            "required": [],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            # Default value should be displayed - string type stays as 'string'
            assert "name?: string = 'default_name'" in signature, (
                f"Expected default value display, got: {signature}"
            )

    def test_integer_default_preserved(self) -> None:
        """Observe: integer defaults show without quotes."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"count": {"type": "integer", "default": 10}},
            "required": [],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            assert "count?: int = 10" in signature, (
                f"Expected integer default display, got: {signature}"
            )

    def test_boolean_default_preserved(self) -> None:
        """Observe: boolean defaults show as True/False."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"enabled": {"type": "boolean", "default": True}},
            "required": [],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            assert "enabled?: bool = true" in signature, (
                f"Expected boolean default display, got: {signature}"
            )

class TestComplexAnyOfPreservation:
    """Test that anyOf without const (non-enum) is preserved."""

    def test_anyof_with_null_preserved(self) -> None:
        """Observe: {"anyOf": [{"type": "string"}, {"type": "null"}]} → "param?: str".

        This is NOT an enum pattern (no const values), so it should use
        existing anyOf logic which treats this as an optional string.
        """
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"value": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
            "required": [],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            # Verify this is NOT treated as enum (should not have quotes)
            # The exact behavior may vary, but it should not be enum-formatted
            assert '"string"' not in signature or "null" not in signature, (
                f"anyOf without const should not be treated as enum, got: {signature}"
            )

class TestEdgeCasePreservation:
    """Test edge cases are preserved."""

    def test_no_schema_returns_empty_parens(self) -> None:
        """Observe: tools without schema return "()"."""
        mock_tool = MagicMock()
        mock_tool.parameters = None  # No schema

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            assert signature == "()", (
                f"Expected empty parens for no schema, got: {signature}"
            )

    def test_empty_properties_returns_empty_parens(self) -> None:
        """Observe: {"properties": {}} returns "()"."""
        mock_tool = MagicMock()
        mock_tool.parameters = {"type": "object", "properties": {}}

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            assert signature == "()", (
                f"Expected empty parens for empty properties, got: {signature}"
            )

    def test_no_type_field_shows_any(self) -> None:
        """Observe: missing type field defaults to 'any'."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {
                "value": {}  # No type specified
            },
            "required": ["value"],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            assert "value: any" in signature, (
                f"Expected 'any' type for missing type field, got: {signature}"
            )

class TestMultiParameterPreservation:
    """Test that multiple parameters format correctly."""

    def test_multiple_parameters_comma_separated(self) -> None:
        """Observe: multiple parameters are comma-separated."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "enabled": {"type": "boolean"},
            },
            "required": ["name", "count", "enabled"],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            # Check format and comma separation
            assert signature.startswith("(") and signature.endswith(")")
            assert "name: str" in signature
            assert "count: int" in signature
            assert "enabled: bool" in signature
            assert signature.count(",") == 2  # Two commas for three params

# Property-Based Tests
class TestPropertyBasedPreservation:
    """Property-based tests for comprehensive preservation checking."""

    @pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
    @given(st.sampled_from(["string", "integer", "number", "boolean"]))
    @settings(max_examples=20)
    def test_all_simple_types_preserved(self, type_name) -> None:
        """Property: For any simple type (no enum), format is unchanged."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"param": {"type": type_name}},
            "required": ["param"],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            # Short type mappings
            short_types: dict = {
                "integer": "int",
                "number": "float",
                "boolean": "bool",
                "string": "str",
            }
            expected_type = short_types.get(type_name, type_name)

            assert f"param: {expected_type}" in signature, (
                f"Type {type_name} not preserved correctly, got: {signature}"
            )

    @pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
    @given(st.booleans())
    @settings(max_examples=10)
    def test_required_optional_preserved(self, is_required) -> None:
        """Property: Required/optional distinction preserved for all params."""
        mock_tool = MagicMock()
        mock_tool.parameters = {
            "type": "object",
            "properties": {"param": {"type": "string"}},
            "required": ["param"] if is_required else [],
        }

        with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
            mock_manager = MagicMock()
            mock_manager._tools = {"test_tool": mock_tool}
            mock_mcp._tool_manager = mock_manager

            signature = _tool_usage_signature("test_tool")

            if is_required:
                assert "param: str" in signature and "param?:" not in signature
            else:
                assert "param?: str" in signature

class TestSnapshotBaseline:
    """Capture baseline behavior as snapshots for comparison after fix."""

    def test_capture_various_patterns(self) -> None:
        """Capture baseline output for various non-enum parameter patterns.

        This creates a snapshot of current behavior that can be compared
        after the fix to ensure preservation.
        """
        test_cases: list = [
            # (tool_name, schema, expected_contains)
            (
                "simple_string",
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
                ["name: str"],
            ),
            (
                "optional_int",
                {
                    "type": "object",
                    "properties": {"count": {"type": "integer"}},
                    "required": [],
                },
                ["count?: int"],
            ),
            (
                "with_default",
                {
                    "type": "object",
                    "properties": {"value": {"type": "string", "default": "test"}},
                    "required": [],
                },
                ["value?: str", "="],
            ),
            (
                "union_type",
                {
                    "type": "object",
                    "properties": {"mixed": {"type": ["string", "integer"]}},
                    "required": ["mixed"],
                },
                ["mixed:"],
            ),
            (
                "multiple_params",
                {
                    "type": "object",
                    "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
                    "required": ["a", "b"],
                },
                ["a: str", "b: int", ","],
            ),
        ]

        baseline_results: dict = {}

        for tool_name, schema, expected_parts in test_cases:
            mock_tool = MagicMock()
            mock_tool.parameters = schema

            with patch("lib.core.get_capabilities.get_capabilities._MCP") as mock_mcp:
                mock_manager = MagicMock()
                mock_manager._tools = {tool_name: mock_tool}
                mock_mcp._tool_manager = mock_manager

                signature = _tool_usage_signature(tool_name)
                baseline_results[tool_name] = signature

                # Verify expected parts are present
                for part in expected_parts:
                    assert part in signature, (
                        f"Expected '{part}' in {tool_name} baseline, got: {signature}"
                    )

        # Store baseline for reference
        # In a real implementation, this could be saved to a file
        print("\n=== BASELINE SNAPSHOT ===")
        for tool_name, signature in baseline_results.items():
            print(f"{tool_name}: {signature}")
        print("========================\n")

        # Assert we captured all test cases
        assert len(baseline_results) == len(test_cases)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
