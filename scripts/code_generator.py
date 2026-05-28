import json, sys, os, subprocess, time, requests
from pathlib import Path

HF_URL = "https://api-inference.huggingface.co/models/hwding/forge-coder-v1.21.11"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"
MAX_FIX_ATTEMPTS = 3

def call_hf(prompt, hf_token, retries=3):
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json",
        "User-Agent": "ModPipeline/1.0"
    }
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": 2048, "temperature": 0.7}}
    for i in range(retries):
        try:
            resp = requests.post(HF_URL, headers=headers, json=payload, timeout=180)
            if resp.status_code == 429:
                wait = 10 * (i+1)
                print(f"HF rate limit, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            result = resp.json()
            if isinstance(result, list) and 'generated_text' in result[0]:
                return result[0]['generated_text']
            else:
                return result[0]['generated_text'] if isinstance(result, list) else str(result)
        except Exception as e:
            print(f"HF attempt {i+1} failed: {e}")
            if i == retries - 1:
                raise
            time.sleep(10)

def call_gemini(prompt, api_key, retries=3, model="gemini-1.5-flash"):
    headers = {"Content-Type": "application/json", "User-Agent": "ModPipeline/1.0"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent"
    for i in range(retries):
        try:
            resp = requests.post(f"{url}?key={api_key}", headers=headers, json=payload, timeout=120)
            if resp.status_code == 429:
                wait = 2 ** i + 5
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            text = data['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text)
        except Exception as e:
            print(f"Gemini attempt {i+1} failed: {e}")
            if i == retries - 1:
                if model == "gemini-1.5-flash":
                    print("Trying model 'gemini-1.5-flash-latest'...")
                    return call_gemini(prompt, api_key, retries=1, model="gemini-1.5-flash-latest")
                raise
            time.sleep(5)

def write_files(file_dict, base="src/main/java"):
    for path, content in file_dict.items():
        full_path = Path(base) / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)

def compile_project():
    res = subprocess.run(["./gradlew", "build"], capture_output=True, text=True, cwd=".")
    return res.returncode == 0, res.stderr + "\n" + res.stdout

def generate_code(modspec_path, output_dir):
    with open(modspec_path, 'r') as f:
        modspec = json.load(f)

    prompt = f"""
Generate a complete Minecraft Forge mod for version {modspec['mc_version']} based on the following modspec.
The mod must include:
- A main mod class with @Mod annotation
- Registration for all items, blocks (if any), and entities (mobs)
- Proper event handlers
- All classes in the package com.{modspec['modid']}
- Use correct Forge registries and deferred registers
- Include a build.gradle file with the correct Forge MDK settings.

Return ONLY a JSON object where keys are file paths relative to src/main/java/ (or build.gradle) and values are the complete file contents.
For example:
{{
  "build.gradle": "...",
  "com/example/modid/ModMain.java": "...",
  ...
}}

Modspec:
{json.dumps(modspec, indent=2)}
"""
    hf_token = os.environ['HF_TOKEN']
    raw_output = call_hf(prompt, hf_token)

    try:
        files_dict = json.loads(raw_output)
    except (json.JSONDecodeError, TypeError):
        print("Forge Coder output not JSON, using Gemini to extract...")
        reformat_prompt = f"""
Convert the following raw AI output into a valid JSON object with file paths as keys and content as values. Output ONLY the JSON.
Raw output:
{raw_output}
"""
        files_dict = call_gemini(reformat_prompt, os.environ['GEMINI_API_KEY'])

    write_files(files_dict, output_dir)

    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        success, error_msg = compile_project()
        if success:
            print("Compilation successful!")
            return
        print(f"Compilation error (attempt {attempt}):\n{error_msg}")
        if attempt == MAX_FIX_ATTEMPTS:
            raise RuntimeError("Failed to fix compilation errors after max attempts.")
        fix_prompt = f"""
The following Java project failed to build. The modspec and current file contents are provided below.
Please fix the compilation errors and return the corrected files as a JSON object (same format as before: keys=paths, values=content).
Only output the JSON.

Modspec:
{json.dumps(modspec, indent=2)}
Current files:
{json.dumps(files_dict, indent=2)}
Build errors:
{error_msg}
"""
        fixed_files = call_gemini(fix_prompt, os.environ['GEMINI_API_KEY'])
        files_dict.update(fixed_files)
        write_files(fixed_files, output_dir)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python code_generator.py <modspec_json> <output_source_dir>")
        sys.exit(1)
    generate_code(sys.argv[1], sys.argv[2])
