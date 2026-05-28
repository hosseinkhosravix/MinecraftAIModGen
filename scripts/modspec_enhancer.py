import json, sys, os, hashlib, time, requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache(prompt):
    h = hashlib.md5(prompt.encode()).hexdigest()
    cache_file = os.path.join(CACHE_DIR, h + ".json")
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return json.load(f)
    return None

def set_cache(prompt, data):
    h = hashlib.md5(prompt.encode()).hexdigest()
    with open(os.path.join(CACHE_DIR, h + ".json"), 'w') as f:
        json.dump(data, f)

def call_gemini(prompt, api_key, retries=3):
    cached = get_cache(prompt)
    if cached:
        print("Using cached Gemini response.")
        return cached

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ModPipeline/1.0 (GitHub Actions)"
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    for i in range(retries):
        try:
            resp = requests.post(
                f"{GEMINI_URL}?key={api_key}",
                headers=headers,
                json=payload,
                timeout=120
            )
            if resp.status_code == 429:
                wait = 2 ** i + 5
                print(f"Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            text = data['candidates'][0]['content']['parts'][0]['text']
            result = json.loads(text)
            set_cache(prompt, result)
            return result
        except Exception as e:
            print(f"Gemini attempt {i+1} failed: {e}")
            if i == retries - 1:
                raise
            time.sleep(5)

def enhance(input_path, output_path):
    with open(input_path, 'r') as f:
        raw = json.load(f)

    prompt = f"""
You are a Minecraft modding expert. Given the raw modspec below, fill missing fields, balance stats, ensure all IDs are lowercase_with_underscores, and return a complete, valid JSON modspec. Add pack_format based on mc_version ({raw.get('mc_version','1.20.1')}). Output ONLY JSON.

Raw spec:
{json.dumps(raw, indent=2)}
"""
    api_key = os.environ['GEMINI_API_KEY']
    enriched = call_gemini(prompt, api_key)

    # Basic integrity checks
    for key in ["mod_name","modid","version","mc_version","loader","description","items","mobs"]:
        if key not in enriched:
            enriched[key] = raw.get(key, "")
    enriched["version"] = str(enriched.get("version","1.0.0"))
    enriched["mc_version"] = str(enriched.get("mc_version","1.20.1"))

    mc_minor = enriched["mc_version"].split(".")[1] if "." in enriched["mc_version"] else "20"
    pf_map = {"20":15, "19":13, "18":12}
    enriched["pack_format"] = pf_map.get(mc_minor, 15)

    with open(output_path, "w") as f:
        json.dump(enriched, f, indent=2)
    print(f"Enriched modspec saved to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python modspec_enhancer.py <input_json> <output_json>")
        sys.exit(1)
    enhance(sys.argv[1], sys.argv[2])
