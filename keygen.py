#!/usr/bin/env python3
"""
ArchiBox USB Key Generator
Run once per new USB key to generate token.txt + config.json
"""
import uuid
import json
import os

def main():
    token = str(uuid.uuid4())
    print(f"Token généré : {token}")
    print()

    # Get device ID
    device_id = input("Device ID [esp32s3-box-01] : ").strip()
    if not device_id:
        device_id = "esp32s3-box-01"

    archimade_host = input("Archimade host [192.168.0.119] : ").strip()
    if not archimade_host:
        archimade_host = "192.168.0.119"

    port = input("Archimade port [8766] : ").strip()
    if not port:
        port = "8766"

    key_path = input("Chemin de la clé USB (ex: D:\\\\) : ").strip().rstrip("\\").rstrip("/")

    if not key_path:
        print("Abandon.")
        return

    # Write files
    token_file = os.path.join(key_path, "token.txt")
    config_file = os.path.join(key_path, "config.json")
    marker_file = os.path.join(key_path, "archibox.key")

    with open(token_file, "w") as f:
        f.write(token)
    print(f"  ✅ {token_file}")

    config = {
        "device_id": device_id,
        "archimade_host": archimade_host,
        "archimade_port": int(port)
    }
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)
    print(f"  ✅ {config_file}")

    with open(marker_file, "w") as f:
        f.write("ArchiBox")
    print(f"  ✅ {marker_file}")

    print()
    print("=" * 40)
    print("Clé USB prête !")
    print(f"Token : {token}")
    print()
    print("IMPORTANT : note ce token quelque part (ex: gestionnaire de mots de passe)")
    print("Si tu perds le token, tu devras en générer un nouveau et le communiquer à archimade.")
    print("=" * 40)

if __name__ == "__main__":
    main()
