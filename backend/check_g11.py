#!/usr/bin/env python
with open(r'D:\StudyAI\backend/providers/llm/chain.py') as f:
    content = f.read()
results = []
if 'PROMPT_INJECTION_DIRECTIVE' in content:
    results.append('G11: PROMPT_INJECTION_DIRECTIVE found')
else:
    results.append('G11: PROMPT_INJECTION_DIRECTIVE not found')

if '<source' in content:
    results.append('G11: <source> wrapper found')
else:
    results.append('G11: <source> wrapper not found')

if 'untrusted' in content.lower():
    results.append('G11: untrusted content instruction found')
else:
    results.append('G11: untrusted content instruction not found')

for r in results:
    print(r)