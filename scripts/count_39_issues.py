import os

base = r'D:\StudyAI\backend'
patterns = ['str | None', 'type | dict']
count = 0
found = set()

for root, dirs, files in os.walk(base):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if not f.endswith('.py'):
            continue
        fp = os.path.join(root, f)
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                content = fh.read()
                for p in patterns:
                    if p in content:
                        found.add(fp)
                        count += 1
        except:
            pass

print(f"Files with Python 3.9 incompatible type annotations: {count}")
print(f"Unique files: {len(found)}")
for f in sorted(found)[:30]:
    print(f"  {f}")