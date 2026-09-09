import os
import re

base = r'D:\StudyAI\backend'
fixed_files = []

for root, dirs, files in os.walk(base):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if not f.endswith('.py'):
            continue
        fp = os.path.join(root, f)
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                content = fh.read()
            
            original = content
            
            # Replace all Python 3.9 incompatible type annotation patterns
            content = content.replace('str | None', 'Optional[str]')
            content = content.replace('float | None', 'Optional[float]')
            content = content.replace('bool | None', 'Optional[bool]')
            content = content.replace('dict | None', 'Optional[dict]')
            content = content.replace('list[dict] | None', 'Optional[list[dict]]')
            content = content.replace('dict | list', 'Union[dict, list]')
            content = content.replace('MasteryScore | None', 'Union[MasteryScore, None]')
            
            # Add typing imports if needed
            if 'Optional' in content and 'from typing import Optional' not in content:
                # Add after the first import line
                first_import_end = content.find('\n')
                if first_import_end > 0:
                    # Find a good place to add the import
                    lines = content.split('\n', 2)
                    if len(lines) >= 3:
                        lines[1] = lines[1] + '\nfrom typing import Optional'
                        content = '\n'.join(lines[:3])
            
            if Union := content.count('Union['):
                if 'from typing import Union' not in content:
                    first_import_end = content.find('\n')
                    if first_import_end > 0:
                        lines = content.split('\n', 2)
                        if len(lines) >= 3:
                            lines[1] = lines[1] + '\nfrom typing import Union'
                            content = '\n'.join(lines[:3])
            
            if content != original:
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(content)
                fixed_files.append(fp)
                print(f"Fixed: {fp}")
        except Exception as e:
            print(f"Error with {fp}: {e}")

print(f"\nTotal files fixed: {len(fixed_files)}")