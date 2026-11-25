#!/bin/bash
cd /opt/handy-coder-mcp
/opt/handy-coder-mcp/.venv/bin/python -m pytest test/test_run_tests_timeout_integration.py -v --tb=short
