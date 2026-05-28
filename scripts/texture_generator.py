import json, sys, os, time, requests, base64
from PIL import Image
from io import BytesIO

MODELSLAB_URL = "https://modelslab.com/api/v3/text2img"
FALLBACK = "assets/fallback.png"

def call_modelslab(prompt, api_key, retries=3):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "ModPipeline/1.0"
    }
    payload = {
        "key": api_key,
        "model_id": "magic-pixel-art-v1",  # their Minecraft‑oriented model
        "prompt": prompt,
        "width": 16,
        "height": 16,
        "samples": 1,
        "num_inference_steps": 20,
        "safety_checker": False,
        "enhance_prompt": False,
        "webhook": None,
        "track_id": None
    }
    for i in range(retries):
        try:
            resp = requests.post(MODELSLAB_URL, json=payload, timeout=60)
            if resp.status_code == 429:
                wait = 15 * (i+1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "success":
                img_b64 = data["output"][0]
                return Image.open(BytesIO(base64.b64decode(img_b64)))
            else:
                raise RuntimeError(f"ModelsLab error: {data}")
        except Exception as e:
            print(f"ModelsLab attempt {i+1} failed: {e}")
            if i == retries-1: raise
            time.sleep(10)

def validate(img):
    return img.size in ((16,16),(32,32)) and img.convert("L").getextrema()[1] > 20

def generate(modspec_path, assets_dir):
    with open(modspec_path) as f: modspec = json.load(f)
    api_key = os.environ["MODELSLAB_API_KEY"]
    modid = modspec["modid"]
    base = os.path.join(assets_dir, modid, "textures")
    os.makedirs(f"{base}/item", exist_ok=True)
    os.makedirs(f"{base}/entity", exist_ok=True)

    if not os.path.exists(FALLBACK):
        Image.new('RGBA', (16,16), (255,0,255)).save(FALLBACK)

    for item in modspec.get("items", []):
        fpath = f"{base}/item/{item['id']}.png"
        if os.path.exists(fpath): continue
        prompt = f"pixel art, 16x16, Minecraft style, {item.get('texture_description', item['name'])}"
        try:
            img = call_modelslab(prompt, api_key)
            if not validate(img):
                img = call_modelslab(prompt + " high quality, sharp", api_key)
                if not validate(img): img = Image.open(FALLBACK)
            img.save(fpath)
        except Exception as e:
            print(f"Failed texture for {item['id']}, using fallback. {e}")
            Image.open(FALLBACK).save(fpath)

    for mob in modspec.get("mobs", []):
        fpath = f"{base}/entity/{mob['id']}.png"
        if os.path.exists(fpath): continue
        prompt = f"pixel art, 16x16, Minecraft {mob.get('texture_description', mob['name'])}"
        try:
            img = call_modelslab(prompt, api_key)
            if not validate(img):
                img = call_modelslab(prompt + " detailed, correct", api_key)
                if not validate(img): img = Image.open(FALLBACK)
            img.save(fpath)
        except Exception as e:
            print(f"Failed texture for {mob['id']}, fallback. {e}")
            Image.open(FALLBACK).save(fpath)

if __name__ == "__main__":
    if len(sys.argv)!=3: sys.exit(1)
    generate(sys.argv[1], sys.argv[2])
