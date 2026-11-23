#!/usr/bin/env python3
"""Simple test to demonstrate the enum bug."""

from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, '/opt/handy-coder-mcp')

from lib.core.get_capabilities.get_capabilities import _tool_usage_signature

def test_string_enum():
    """Test that string enum values should be embedded in usage signatures."""
    # Create a mock tool with string enum parameter
    mock_tool = MagicMock()
    mock_tool.parameters = {
        'type': 'object',
        'properties': {
            'action': {
                'type': 'string',
                'enum': ['foo', 'bar', 'baz']
            }
        },
        'required': ['action']
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {'test_tool': mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature('test_tool')
        print(f'Signature: {signature}')
        
        # Check if enum values are present
        has_enum = '"foo"|"bar"|"baz"' in signature
        print(f'Contains enum values: {has_enum}')
        
        if not has_enum:
            print('BUG CONFIRMED: Enum values are NOT embedded in the signature')
            print('Expected: (action: "foo"|"bar"|"baz")')
            print(f'Got: {signature}')
        else:
            print('SUCCESS: Enum values ARE embedded in the signature')
        
        return has_enum

def test_integer_enum():
    """Test that integer enum values should be embedded in usage signatures."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        'type': 'object',
        'properties': {
            'priority': {
                'type': 'integer',
                'enum': [1, 2, 3]
            }
        },
        'required': ['priority']
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {'test_tool': mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature('test_tool')
        print(f'\nSignature: {signature}')
        
        has_enum = '1|2|3' in signature
        print(f'Contains enum values: {has_enum}')
        
        if not has_enum:
            print('BUG CONFIRMED: Integer enum values are NOT embedded in the signature')
            print('Expected: (priority: 1|2|3)')
            print(f'Got: {signature}')
        else:
            print('SUCCESS: Integer enum values ARE embedded in the signature')
        
        return has_enum

def test_anyof_const():
    """Test that anyOf with const pattern should be embedded in usage signatures."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        'type': 'object',
        'properties': {
            'mode': {
                'anyOf': [
                    {'const': 'read', 'type': 'string'},
                    {'const': 'write', 'type': 'string'}
                ]
            }
        },
        'required': ['mode']
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {'test_tool': mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature('test_tool')
        print(f'\nSignature: {signature}')
        
        has_enum = '"read"|"write"' in signature
        print(f'Contains enum values: {has_enum}')
        
        if not has_enum:
            print('BUG CONFIRMED: anyOf const values are NOT embedded in the signature')
            print('Expected: (mode: "read"|"write")')
            print(f'Got: {signature}')
        else:
            print('SUCCESS: anyOf const values ARE embedded in the signature')
        
        return has_enum

def test_git_manage_action():
    """Test git_manage action parameter with 14 enum values."""
    mock_tool = MagicMock()
    mock_tool.parameters = {
        'type': 'object',
        'properties': {
            'action': {
                'type': 'string',
                'enum': [
                    'status', 'diff', 'log', 'add', 'commit', 'push', 
                    'pull', 'merge', 'rebase', 'checkout', 'branch', 
                    'stash', 'blame', 'init'
                ],
                'description': 'Git action to perform'
            }
        },
        'required': ['action']
    }
    
    with patch('lib.core.get_capabilities.get_capabilities._MCP') as mock_mcp:
        mock_manager = MagicMock()
        mock_manager._tools = {'git_manage': mock_tool}
        mock_mcp._tool_manager = mock_manager
        
        signature = _tool_usage_signature('git_manage')
        print(f'\nSignature: {signature}')
        
        # Check if all actions are present
        expected_actions = [
            'status', 'diff', 'log', 'add', 'commit', 'push',
            'pull', 'merge', 'rebase', 'checkout', 'branch',
            'stash', 'blame', 'init'
        ]
        
        all_present = all(f'"{action}"' in signature for action in expected_actions)
        print(f'All 14 actions present: {all_present}')
        
        if not all_present:
            print('BUG CONFIRMED: git_manage action enum values are NOT all embedded in the signature')
            print('Expected all 14 actions in signature')
            print(f'Got: {signature}')
        else:
            print('SUCCESS: All git_manage action enum values ARE embedded in the signature')
        
        return all_present


if __name__ == '__main__':
    print('=' * 70)
    print('BUG EXPLORATION TEST - Testing on UNFIXED code')
    print('These tests are EXPECTED TO FAIL on unfixed code')
    print('=' * 70)
    
    results = []
    
    print('\n--- Test 1: String Enum ---')
    results.append(('String Enum', test_string_enum()))
    
    print('\n--- Test 2: Integer Enum ---')
    results.append(('Integer Enum', test_integer_enum()))
    
    print('\n--- Test 3: anyOf Const ---')
    results.append(('anyOf Const', test_anyof_const()))
    
    print('\n--- Test 4: git_manage Action (Real Integration Test) ---')
    results.append(('git_manage Action', test_git_manage_action()))
    
    print('\n' + '=' * 70)
    print('SUMMARY')
    print('=' * 70)
    
    failed_tests = [name for name, passed in results if not passed]
    
    if failed_tests:
        print(f'\n{len(failed_tests)} test(s) FAILED (as expected on unfixed code):')
        for name in failed_tests:
            print(f'  - {name}')
        print('\nThis confirms the bug exists:')
        print('Enum values are NOT embedded in usage signatures on unfixed code.')
    else:
        print('\nAll tests PASSED unexpectedly!')
        print('This suggests the code may already be fixed.')
    
    print('\n' + '=' * 70)
