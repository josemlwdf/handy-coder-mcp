import base64

# Read the current test file and extract exact text of the two failing methods
with open('test/test_apply_edits_b64.py', encoding='utf-8') as f:
    src = f.read()

# Find start/end of each method by scanning lines
lines = src.splitlines(keepends=True)

def find_method_range(lines, def_name):
    """Return (start_idx, end_idx) line indices of a method block."""
    start = None
    for i, line in enumerate(lines):
        if def_name in line and line.lstrip().startswith('def '):
            start = i
            break
    if start is None:
        raise ValueError(f'Method {def_name} not found')
    # Method ends when we see a line at the same or lower indent that starts 'def '
    # or end of file
    base_indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].lstrip()
        if stripped.startswith('def ') or stripped.startswith('class '):
            indent = len(lines[i]) - len(stripped)
            if indent <= base_indent:
                end = i
                break
    return start, end

bs_start, bs_end = find_method_range(lines, 'test_backslash_heavy_pattern_via_b64')
ml_start, ml_end = find_method_range(lines, 'test_multiline_replacement_via_b64')

bs_text = ''.join(lines[bs_start:bs_end])
ml_text = ''.join(lines[ml_start:ml_end])

print('=== BACKSLASH METHOD (current) ===')
print(repr(bs_text[:200]))
print()
print('=== MULTILINE METHOD (current) ===')
print(repr(ml_text[:200]))
print()

# Build corrected versions
new_bs = bs_text.replace(
    'target = self.root / "code.py"',
    'target = self.root / "paths.txt"  # .txt avoids Python code polish'
).replace(
    'path="code.py"',
    'path="paths.txt"'
)

new_ml = ml_text.replace(
    'target = self.root / "config.py"',
    'target = self.root / "config.txt"  # .txt avoids Python code polish'
).replace(
    'path="config.py"',
    'path="config.txt"'
)

print('=== PATTERN b64 for backslash method ===')
print(base64.b64encode(bs_text.rstrip().encode()).decode())
print()
print('=== REPLACEMENT b64 for backslash method ===')
print(base64.b64encode(new_bs.rstrip().encode()).decode())
print()
print('=== PATTERN b64 for multiline method ===')
print(base64.b64encode(ml_text.rstrip().encode()).decode())
print()
print('=== REPLACEMENT b64 for multiline method ===')
print(base64.b64encode(new_ml.rstrip().encode()).decode())
