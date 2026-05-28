import json, sys, os, hashlib, time, requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def cache_get(prompt):
    h = hashlib.md5(prompt.encode()).hexdigest()
    path = os.path.join(CACHE_DIR, h+".json")
    if os.path.exists(path):
        with open(path) as f: return json.load(f)
    return None

def cache_set(prompt, data):
    h = hashlib.md5(prompt.encode()).hexdigest()
    with open(os.path.join(CACHE_DIR, h+".json"), "w") as f:
        json.dump(data, f)

def call_openrouter(messages, api_key, model="google/gemini-2.0-flash-exp:free", retries=3):
    cached = cache_get(str(messages))
    if cached: return cached

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "ModPipeline/1.0"
    }
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"}  # many models support this
    }
    for i in range(retries):
        try:
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
            if resp.status_code == 429:
                wait = 2**i + 5
                print(f"Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)
            cache_set(str(messages), result)
            return result
        except Exception as e:
            print(f"OpenRouter attempt {i+1} failed: {e}")
            if i == retries-1: raise
            time.sleep(10)

def enhance(input_path, output_path):
    with open(input_path) as f: raw = json.load(f)

    prompt = f"""
You are a Minecraft modding expert. Given the raw modspec below, fill missing fields, balance stats, ensure all IDs are lowercase_with_underscores, and return a complete, valid JSON modspec. Add pack_format based on mc_version ({raw.get('mc_version','1.20.1')}). Output ONLY JSON.

Raw spec:
{json.dumps(raw, indent=2)}
"""
    messages = [{"role": "user", "content": prompt}]
    enriched = call_openrouter(messages, os.environ["OPENROUTER_API_KEY"])

    # Basic integrity checks
    for key in ["mod_name","modid","version","mc_version","loader","description","items","mobs"]:
        if key not in enriched: enriched[key] = raw.get(key, "")
    enriched["version"] = str(enriched.get("version","1.0.0"))
    enriched["mc_version"] = str(enriched.get("mc_version","1.20.1"))
    # add pack_format
    mc_minor = enriched["mc_version"].split(".")[1] if "." in enriched["mc_version"] else "20"
    pf_map = {"20":15, "19":13, "18":12}
    enriched["pack_format"] = pf_map.get(mc_minor, 15)

    with open(output_path,"w") as f: json.dump(enriched, f, indent=2)

if __name__ == "__main__":
    if len(sys.argv)!=3: sys.exit(1)
    enhance(sys.argv[1], sys.argv[2])
