#!/usr/bin/env python
"""Verify G5 - Change Magnitude implementation"""
import ast
import sys

with open('apps/ai_classroom/services.py') as f:
    content = f.read()

try:
    tree = ast.parse(content)
    print("OK - File parses successfully")
except SyntaxError as e:
    print(f"FAIL - Syntax error: {e}")
    sys.exit(1)

# Find the _compute_change_magnitude method
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == '_compute_change_magnitude':
        print("\n=== Found _compute_magnitude ===")
    if isinstance(node, ast.FunctionDef) and node.name == '_compute_change_magnitude':
        print("\n=== Found _compute_change_magnitude ===")
        source = ast.get_source_segment(content, node)
        if source:
            print(source)
        
        # Critical checks
        print("\n=== CRITICAL CHECKS ===")
        
        # OLD approach used split("|") on hash strings
        # NEW approach uses content-based Jaccard
        has_hash_jaccard = 'split("|")' in content
        uses_content = '.content' in content
        uses_jaccard = 'jaccard' in content.lower()
        has_magnitude_inversion = '1.0 - jaccard' in content
        has_placeholder = 'return 0.5' in content
        has_no_prev = 'No previous enrichment = maximum change' in content
        
        print(f"Uses hash-based Jaccard (split|): {has_hash_jaccard}")
        print(f"Compares chunk .content: {uses_content}")
        print(f"Uses Jaccard similarity: {uses_jaccard}")
        print(f"Magnitude = 1 - jaccard: {has_magnitude_inversion}")
        print(f"Has old placeholder 0.5: {has_placeholder}")
        print(f"Returns 1.0 if no prev: {has_no_prev}")
        
        # VERDICT
        print("\n=== VERDICT ===")
        if has_hash_jaccard:
            print("FAIL: Uses old hash-based Jaccard (split by |). Magnitude always ~0.5, coalescing broken.")
        elif uses_content and uses_jaccard and has_magnitude_inversion and not has_placeholder:
            print("PASS: Content-based Jaccard similarity. Magnitude varies with actual content change.")
        else:
            print("UNKNOWN: Cannot determine implementation status from source analysis alone.")