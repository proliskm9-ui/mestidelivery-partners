import json
import re
import os

def apply_replacement(content, target, replacement):
    if target not in content:
        print(f"WARNING: Target not found in content!")
        # Let's try matching with normalized whitespace if exact fails
        normalized_target = re.sub(r'\s+', '', target)
        normalized_content = re.sub(r'\s+', '', content)
        if normalized_target in normalized_content:
            print("INFO: Found target with normalized whitespace, doing regex replace...")
            # We can build a regex that allows arbitrary whitespace between tokens of the target
            # Escape regex special characters in target
            escaped_target = re.escape(target)
            # Replace whitespace sequences in escaped target with \s*
            regex_pattern = re.sub(r'\\\s+', r'\s+', escaped_target)
            return re.sub(regex_pattern, replacement, content, count=1)
        return content.replace(target, replacement)
    return content.replace(target, replacement)

def main():
    prev_log_path = r"C:\Users\sxclipse\.gemini\antigravity-ide\brain\332e0550-de9c-4065-845f-3c24be6df508\.system_generated\logs\transcript_full.jsonl"
    curr_log_path = r"C:\Users\sxclipse\.gemini\antigravity-ide\brain\b1f4b178-2b2b-4c9a-812e-7ab36a143100\.system_generated\logs\transcript_full.jsonl"
    bot_path = "bot.py"
    
    # 1. Read step 258 of the previous session to get the base bot.py
    base_content = None
    with open(prev_log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                step = json.loads(line)
            except Exception:
                continue
            if step.get("step_index") == 258:
                tool_calls = step.get("tool_calls", [])
                for tc in tool_calls:
                    if tc.get("name") == "write_to_file":
                        args = tc.get("args", {})
                        if isinstance(args, str):
                            args = json.loads(args)
                        base_content = args.get("CodeContent") or args.get("code_content")
                break
                
    if not base_content:
        print("ERROR: Could not find step 258 write_to_file in previous log!")
        return
        
    print(f"Base bot.py length from previous session: {len(base_content)} chars")
    content = base_content
    
    # 2. Read the current session's log and apply all edits up to step 1399
    with open(curr_log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    step_count = 0
    for line in lines:
        try:
            step = json.loads(line)
        except Exception:
            continue
            
        step_index = step.get("step_index")
        
        # We only apply edits before my git checkout/revert steps (which are >= 1400)
        if step_index is not None and step_index >= 1400:
            continue
            
        tool_calls = step.get("tool_calls", [])
        if not tool_calls:
            continue
            
        for tc in tool_calls:
            name = tc.get("name")
            args = tc.get("args", {})
            
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    pass
                    
            target_file = args.get("TargetFile") or args.get("target_file") or ""
            if "bot.py" not in target_file.lower():
                continue
                
            print(f"Applying step {step_index} tool {name}...")
            
            if name == "write_to_file":
                code_content = args.get("CodeContent") or args.get("code_content")
                if code_content:
                    content = code_content
                    step_count += 1
                    
            elif name == "replace_file_content":
                target = args.get("TargetContent") or args.get("target_content")
                replacement = args.get("ReplacementContent") or args.get("replacement_content")
                if target is not None and replacement is not None:
                    content = apply_replacement(content, target, replacement)
                    step_count += 1
                    
            elif name == "multi_replace_file_content":
                chunks = args.get("ReplacementChunks") or args.get("replacement_chunks")
                if chunks:
                    for chunk in chunks:
                        target = chunk.get("TargetContent") or chunk.get("target_content")
                        replacement = chunk.get("ReplacementContent") or chunk.get("replacement_content")
                        if target is not None and replacement is not None:
                            content = apply_replacement(content, target, replacement)
                    step_count += 1
                    
    # Save the reconstructed content
    with open(bot_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Restored bot.py length: {len(content)} chars across {step_count} current-session edit steps.")

if __name__ == "__main__":
    main()
