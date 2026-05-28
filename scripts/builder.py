import json, sys, os, subprocess
from pathlib import Path

def build(modspec_path):
    with open(modspec_path) as f: modspec = json.load(f)
    modid = modspec['modid']
    mc_version = modspec['mc_version']
    pack_format = modspec.get('pack_format', 15)

    # pack.mcmeta
    os.makedirs("assets", exist_ok=True)
    with open("pack.mcmeta", "w") as f:
        json.dump({"pack":{"pack_format": pack_format, "description": modspec.get("description","")}}, f, indent=2)

    if not os.path.exists("build.gradle"):
        # Minimal Forge build.gradle (ensure repo has gradlew)
        print("Warning: No build.gradle found. The code generator should have created one.")
        sys.exit(1)

    res = subprocess.run(["./gradlew", "build"], capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print("Build failed:", res.stderr)
        sys.exit(1)

    jars = list(Path("build/libs").glob("*.jar"))
    if not jars:
        print("No JAR produced.")
        sys.exit(1)
    print(f"Mod built: {jars[0]}")

if __name__ == "__main__":
    if len(sys.argv)!=2: sys.exit(1)
    build(sys.argv[1])
