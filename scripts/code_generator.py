import json, sys, os, subprocess, time, requests
from pathlib import Path

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_FIX_ATTEMPTS = 3

def call_openrouter(messages, api_key, model="google/gemini-2.0-flash-exp:free"):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "ModPipeline/1.0"
    }
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"}
    }
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])

def write_files(file_dict, base="src/main/java"):
    for path, content in file_dict.items():
        full = Path(base) / path
        full.parent.mkdir(parents=True, exist_ok=True)
        with open(full, "w") as f: f.write(content)

def compile_project():
    res = subprocess.run(["./gradlew", "build"], capture_output=True, text=True)
    return res.returncode == 0, res.stderr + "\n" + res.stdout

def generate_code(modspec_path, output_dir):
    with open(modspec_path) as f: modspec = json.load(f)

    prompt = f"""
Generate a complete Minecraft Forge mod (version {modspec['mc_version']}) from this modspec.
Return ONLY a JSON object mapping relative file paths to file contents. Include build.gradle and all Java classes in package com.{modspec['modid']}.
Use proper Forge registries, annotations, and events.

Modspec:
{json.dumps(modspec, indent=2)}
"""
    messages = [{"role":"user","content": prompt}]
    api_key = os.environ["OPENROUTER_API_KEY"]
    files = call_openrouter(messages, api_key)

    write_files(files, output_dir)

    # Self-healing loop
    for attempt in range(1, MAX_FIX_ATTEMPTS+1):
        success, error = compile_project()
        if success:
            print("Compilation OK")
            return
        print(f"Compilation error (attempt {attempt}):\n{error}")
        if attempt == MAX_FIX_ATTEMPTS: raise RuntimeError("Can't fix errors")
        fix_prompt = f"""
Fix these build errors. Return corrected files as JSON (same structure).
Modspec: {json.dumps(modspec)}
Current files: {json.dumps(files)}
Build errors: {error}
"""
        messages = [{"role":"user","content": fix_prompt}]
        fixed = call_openrouter(messages, api_key)
        files.update(fixed)
        write_files(fixed, output_dir)

if __name__ == "__main__":
    if len(sys.argv)!=3: sys.exit(1)
    generate_code(sys.argv[1], sys.argv[2])
