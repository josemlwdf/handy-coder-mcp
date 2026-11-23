#!/usr/bin/env python3
"""Test to understand how Literal enums are represented in JSON schemas."""

from typing import Literal
from typing_extensions import Annotated
from pydantic import Field, TypeAdapter
import json

# Test case 1: Simple Literal
print("=== Test 1: Simple Literal ===")
SimpleEnum = Literal["foo", "bar", "baz"]
adapter1 = TypeAdapter(SimpleEnum)
schema1 = adapter1.json_schema()
print(json.dumps(schema1, indent=2))

# Test case 2: Annotated Literal (like git_manage action)
print("\n=== Test 2: Annotated Literal ===")
AnnotatedEnum = Annotated[
    Literal["status", "diff", "log"],
    Field(description="Git action")
]
adapter2 = TypeAdapter(AnnotatedEnum)
schema2 = adapter2.json_schema()
print(json.dumps(schema2, indent=2))

# Test case 3: Integer Literal
print("\n=== Test 3: Integer Literal ===")
IntEnum = Literal[1, 2, 3]
adapter3 = TypeAdapter(IntEnum)
schema3 = adapter3.json_schema()
print(json.dumps(schema3, indent=2))

# Test case 4: Mixed type Literal
print("\n=== Test 4: Mixed Literal ===")
MixedEnum = Literal["foo", 1, True]
adapter4 = TypeAdapter(MixedEnum)
schema4 = adapter4.json_schema()
print(json.dumps(schema4, indent=2))
