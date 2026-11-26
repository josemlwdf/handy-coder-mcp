"""Property-based tests for comprehensive validation.

Task 5: Use hypothesis to verify properties hold across many generated inputs.

Property 1: Enum values always embedded when present
Property 2: Non-enum formatting preserved
Property 3: Well-formed signature syntax
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

try:
    from hypothesis import given, assume, strategies as st, settings

    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False

    # Provide dummy stubs so class-body decorators don't raise NameError
    class _DummySt:
        """DummySt class."""

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
            import pytest

            def skip_test(self, *a, **kw) -> None:
                """Skip test function."""
                pytest.skip("hypothesis not installed")

            skip_test.__name__ = func.__name__
            return skip_test

        return decorator

    def settings(*args, **kwargs):
        """Settings function."""

        def decorator(func):
            """Decorator function."""
            return func

        return decorator

    # Also stub out strategy variables used at module level
    scalar_values = None
    enum_schema_st = None
    anyof_const_schema_st = None
    non_enum_schema_st = None
    union_non_enum_st = None

from lib.workspace_context.get_capabilities.get_capabilities import (
    _extract_enum_values,
    _format_enum_type,
    _tool_usage_signature,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def has_enum_values(schema: dict) -> bool:
    """Return True if schema contains enum constraints."""
    return _extract_enum_values(schema) is not None

def make_tool_schema(properties: dict, required: list = None) -> dict:
    """Make tool schema function."""
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }

def get_sig(schema: dict, name: str = "test_tool") -> str:
    """Get sig function."""
    mock_tool = MagicMock()
    mock_tool.parameters = schema
    with patch("lib.workspace_context.get_capabilities.get_capabilities._MCP") as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {name: mock_tool}
        mock_mcp._tool_manager = mock_manager
        return _tool_usage_signature(name)

# ── Hypothesis strategies ─────────────────────────────────────────────────────

if HYPOTHESIS_AVAILABLE:
    # Scalar values that can appear in enum lists
    scalar_values = st.one_of(
        st.text(max_size=20),
        st.integers(min_value=-100, max_value=100),
        st.booleans(),
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    )

    # Strategy: enum schema with at least one value
    enum_schema_st = st.fixed_dictionaries(
        {"enum": st.lists(scalar_values, min_size=1, max_size=10)}
    )

    # Strategy: anyOf with const values
    anyof_const_schema_st = st.lists(scalar_values, min_size=1, max_size=8).map(
        lambda vals: {"anyOf": [{"const": v} for v in vals]}
    )

    # Strategy: non-enum schema (plain types)
    non_enum_schema_st = st.fixed_dictionaries(
        {"type": st.sampled_from(["string", "integer", "number", "boolean"])}
    )

    # Strategy: union non-enum
    union_non_enum_st = st.fixed_dictionaries(
        {
            "type": st.lists(
                st.sampled_from(["string", "integer", "number", "boolean", "null"]),
                min_size=2,
                max_size=3,
            )
        }
    )

# ── Property 1: Enum values always embedded when present ──────────────────────

@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestProperty1EnumAlwaysEmbedded:
    """For any schema with enum values, the signature must contain those values."""

    @given(schema=enum_schema_st)
    @settings(max_examples=100)
    def test_enum_field_values_always_in_signature(self, schema) -> None:
        """Every value in an enum field must appear in the usage signature."""
        enum_values = _extract_enum_values(schema)
        assume(enum_values is not None)
        formatted = _format_enum_type(enum_values)
        tool_schema = make_tool_schema({"param": schema}, required=["param"])
        sig = get_sig(tool_schema)
        assert formatted in sig, (
            f"Expected '{formatted}' in signature, got: {sig}\nSchema: {schema}"
        )

    @given(schema=anyof_const_schema_st)
    @settings(max_examples=100)
    def test_anyof_const_values_always_in_signature(self, schema) -> None:
        """Every const value in anyOf must appear in the usage signature."""
        enum_values = _extract_enum_values(schema)
        assume(enum_values is not None)
        formatted = _format_enum_type(enum_values)
        tool_schema = make_tool_schema({"param": schema}, required=["param"])
        sig = get_sig(tool_schema)
        assert formatted in sig, (
            f"Expected '{formatted}' in signature, got: {sig}\nSchema: {schema}"
        )

# ── Property 2: Non-enum formatting preserved ─────────────────────────────────

@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestProperty2NonEnumPreserved:
    """For any schema without enum values, type-based formatting is used."""

    SHORT_TYPES = {"integer": "int", "number": "float", "boolean": "bool"}

    @given(schema=non_enum_schema_st)
    @settings(max_examples=100)
    def test_non_enum_uses_type_based_format(self, schema) -> None:
        """Test non enum uses type based format function."""
        assume(not has_enum_values(schema))
        expected_type = self.SHORT_TYPES.get(schema["type"], schema["type"])
        tool_schema = make_tool_schema({"param": schema}, required=["param"])
        sig = get_sig(tool_schema)
        assert f"param: {expected_type}" in sig, (
            f"Expected 'param: {expected_type}' in signature, got: {sig}"
        )

    @given(schema=union_non_enum_st)
    @settings(max_examples=100)
    def test_union_type_format_preserved(self, schema) -> None:
        """Test union type format preserved function."""
        assume(not has_enum_values(schema))
        short_types = self.SHORT_TYPES
        types = schema["type"]
        expected_type = "|".join(short_types.get(t, t) for t in types)
        tool_schema = make_tool_schema({"param": schema}, required=["param"])
        sig = get_sig(tool_schema)
        assert f"param: {expected_type}" in sig, (
            f"Expected 'param: {expected_type}' in signature, got: {sig}"
        )

# ── Property 3: Well-formed signature syntax ──────────────────────────────────

@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestProperty3WellFormedSyntax:
    """All signatures must have valid balanced-paren syntax."""

    @given(schema=st.one_of(enum_schema_st, non_enum_schema_st))
    @settings(max_examples=150)
    def test_signature_always_parenthesised(self, schema) -> None:
        """Test signature always parenthesised function."""
        tool_schema = make_tool_schema({"param": schema}, required=["param"])
        sig = get_sig(tool_schema)
        assert sig.startswith("("), f"Signature must start with '(', got: {sig}"
        assert sig.endswith(")"), f"Signature must end with ')', got: {sig}"
        assert sig.count("(") == sig.count(")"), (
            f"Unbalanced parentheses in signature: {sig}"
        )

    @given(schema=st.one_of(enum_schema_st, non_enum_schema_st))
    @settings(max_examples=150)
    def test_multi_param_signature_comma_separated(self, schema) -> None:
        """Test multi param signature comma separated function."""
        tool_schema = make_tool_schema(
            {"p1": schema, "p2": {"type": "string"}}, required=["p1", "p2"]
        )
        sig = get_sig(tool_schema)
        assert ", " in sig, f"Multi-param signature must use ', ' separator, got: {sig}"

# ── Determinism tests (no hypothesis needed) ──────────────────────────────────

class TestDeterminism:
    """Signatures are deterministic for a given schema."""

    def test_same_schema_same_signature(self) -> None:
        """Test same schema same signature function."""
        schema = make_tool_schema(
            {"action": {"type": "string", "enum": ["a", "b", "c"]}}, required=["action"]
        )
        sig1 = get_sig(schema)
        sig2 = get_sig(schema)
        assert sig1 == sig2

    def test_format_enum_type_deterministic(self) -> None:
        """Test format enum type deterministic function."""
        values: list = ["foo", "bar", "baz"]
        result1 = _format_enum_type(values)
        result2 = _format_enum_type(values)
        assert result1 == result2
