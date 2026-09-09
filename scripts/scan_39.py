import os
import re

base = r'D:\StudyAI\backend'
issues = []

for root, dirs, files in os.walk(base):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if not f.endswith('.py'):
            continue
        fp = os.path.join(root, f)
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                content = fh.read()
                # Check for Python 3.9 incompatible patterns
                if '| None' in content:
                    for line_num, line in enumerate(content.split('\n'), 1):
                        # Match patterns like: variable: type | None = value
                        # or: function(arg: type | None) -> ...
                        # or: value: type | None
                        if re.search(r'\b\w+\s*\|\s*None\b', line) or re.search(r'\b\w+\s*\[\s*\w+\s*\]\s*\|\s*None\b', line):
                            issues.append((fp, line_num, line.strip()[:90]))
        except:
            pass

# Deduplicate and show unique files
from collections import Counter
file_counts = Counter(issue[0] for issue in issues)
print(f"Files with Python 3.9 type annotation issues: {len(file_counts)}")
for f, count in sorted(file_counts.items())[:30]:
    print(f"  {f} ({count} issues)")