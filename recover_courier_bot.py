import json
import os

logs = [
    r'C:\Users\sxclipse\.gemini\antigravity-ide\brain\c9b8e768-31de-4486-bd1b-a6d683682fac\.system_generated\logs\transcript_full.jsonl',
    r'C:\Users\sxclipse\.gemini\antigravity-ide\brain\ee954864-0fd6-45b5-a463-725bb309914f\.system_generated\logs\transcript_full.jsonl'
]

files_to_recover = ['c:\\bot\\bot.py', 'c:\\bot\\config.py', 'c:\\bot\\keyboards.py', 'c:\\bot\\texts.py']
file_contents = {f: "" for f in files_to_recover}

def apply_replacement(content, target, replacement, start_line, end_line, allow_multiple):
    lines = content.split('\n')
    chunk_lines = lines[start_line-1:end_line]
    chunk = '\n'.join(chunk_lines)
    if allow_multiple:
        new_chunk = chunk.replace(target, replacement)
    else:
        new_chunk = chunk.replace(target, replacement, 1)
    
    new_lines = new_chunk.split('\n')
    lines[start_line-1:end_line] = new_lines
    return '\n'.join(lines)

for log_path in logs:
    if not os.path.exists(log_path): continue
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                step = json.loads(line)
                if 'tool_calls' in step:
                    for tc in step['tool_calls']:
                        args = tc.get('args', {})
                        name = tc.get('name')
                        target_file = args.get('TargetFile', args.get('AbsolutePath', '')).lower()
                        if target_file in files_to_recover:
                            if name == 'write_to_file':
                                file_contents[target_file] = args.get('CodeContent', '')
                            elif name == 'replace_file_content':
                                file_contents[target_file] = apply_replacement(
                                    file_contents[target_file],
                                    args.get('TargetContent', ''),
                                    args.get('ReplacementContent', ''),
                                    int(args.get('StartLine', 1)),
                                    int(args.get('EndLine', 1)),
                                    args.get('AllowMultiple', False) == 'true'
                                )
            except Exception as e:
                pass

for f_path, content in file_contents.items():
    if content.strip():
        with open(f_path, 'w', encoding='utf-8') as out:
            out.write(content)
        print(f"Recovered {f_path} ({len(content)} chars)")
