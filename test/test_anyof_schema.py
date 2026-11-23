#!/usr/bin/env python3
"""Test to understand anyOf representations in JSON schemas."""

from typing import Union, Literal
from pydantic import TypeAdapter
import json

# Test case 1: Union of Literals
print("=== Test 1: Union of Literals ===")
UnionEnum = Union[Literal["foo"], Literal["bar"], Literal["baz"]]
adapter1 = TypeAdapter(UnionEnum)
schema1 = adapter1.json_schema()
print(json.dumps(schema1, indent=2))

# Test case 2: Union with const values (older style)
print("\n=== Test 2: Optional string ===")
OptionalStr = Union[str, None]
adapter2 = TypeAdapter(OptionalStr)
schema2 = adapter2.json_schema()
print(json.dumps(schema2, indent=2))
