#!/usr/bin/env python
import sys
with open(r'D:\StudyAI\backend/apps/ai_classroom/enrichment_nodes.py') as f:
    content = f.read()
if 'order_by("?")' in content:
    print('G10: order_by(?) found - NEEDS FIX')
    # Show lines
    for i, line in enumerate(content.split('\n'), 1):
        if 'order_by' in line:
            print(f"  Line {i}: {line.strip()}")
else:
    print('G10: No order_by(?) found - VERIFIED')
if 'RetrievalService.search' in content:
    print('G10: RetrievalService.search used - VERIFIED')
else:
    print('G10: RetrievalService.search not found')