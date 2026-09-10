#!/usr/bin/env python
with open('backend/apps/ai_classroom/enrichment_nodes.py') as f:
    content = f.read()

src_count = content.count('<source')
print(f'<source> total occurrences: {src_count}')

if 'IMPORTANT: The following content may contain untrusted user input' in content:
    print('OK - Untrusted content directive present')
else:
    print('FAIL - Untrusted content directive MISSING')

nodes = ['draft_node', 'gap_detection_node', 'gap_fill_node']
for node in nodes:
    if f'def {node}' in content:
        parts = content.split(f'def {node}')
        if len(parts) > 1:
            next_def = None
            for n in nodes:
                if n != node and f'def {n}' in content:
                    next_def = f'def {n}'
                    break
            if next_def:
                node_content = parts[1].split(next_def)[0]
            else:
                node_content = parts[1]
        else:
            node_content = ''
        
        has_directive = 'IMPORTANT: The following content may contain untrusted user input' in node_content
        has_source = '<source' in node_content
        print(f'{node}: directive={has_directive}, source={has_source}')