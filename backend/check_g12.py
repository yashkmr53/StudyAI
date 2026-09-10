#!/usr/bin/env python
with open(r'D:\StudyAI\backend/providers/llm/chain.py') as f:
    content = f.read()
results = []
if '_sanitize_for_provider' in content:
    results.append('G12: _sanitize_for_provider found')
else:
    results.append('G12: _sanitize_for_provider not found')

if '_REDACTION_PATTERNS' in content:
    results.append('G12: _REDACTION_PATTERNS found')
else:
    results.append('G12: _REDACTION_PATTERNS not found')

if '\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b' in content:
    results.append('G12: Email redaction pattern found')
else:
    results.append('G12: Email redaction pattern not found')

for r in results:
    print(r)