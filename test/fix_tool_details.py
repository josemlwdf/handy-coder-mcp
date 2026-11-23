content = open('/opt/handy-coder-mcp/lib/tool_details.py').read()

old = '''
        schema = copy.deepcopy(entry["inputSchema"])
        arguments = _arguments(schema)
        arguments = {
            name: {
                "type": detail["type"],
                "required": detail["required"],
                "description": _brief(detail["description"]),
            }
            for name, detail in arguments.items()
        }'''

new = '''
        schema = copy.deepcopy(entry["inputSchema"])
        arguments = _arguments(schema)

        def _compact_detail(detail: dict) -> dict:
            item: dict = {
                "type": detail["type"],
                "required": detail["required"],
                "description": _brief(detail["description"]),
            }
            if "default" in detail:
                item["default"] = detail["default"]
            constraints = detail.get("constraints", {})
            if "enum" in constraints:
                item["enum"] = constraints["enum"]
            return item

        arguments = {name: _compact_detail(detail) for name, detail in arguments.items()}'''

assert old in content, 'Pattern not found!'
new_content = content.replace(old, new, 1)
open('/opt/handy-coder-mcp/lib/tool_details.py', 'w').write(new_content)
print('Done, wrote', len(new_content), 'bytes')
