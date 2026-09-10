#!/usr/bin/env python
with open(r'D:\StudyAI\backend/apps/documents/services.py') as f:
    content = f.read()
if 'select_for_update' in content:
    print('G15: select_for_update found - VERIFIED')
else:
    print('G15: select_for_update not found - NEEDS FIX')
if '_create_revision_locked' in content:
    print('G15: _create_revision_locked found')
EOF