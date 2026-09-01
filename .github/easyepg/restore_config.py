import argparse
import base64
import os
from pathlib import Path


def decode_secret(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"GitHub secret {name} is missing")
    return base64.b64decode(value, validate=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("storage")
    args = parser.parse_args()

    storage = Path(args.storage)
    storage.mkdir(parents=True, exist_ok=True)
    (storage / "settings.json").write_bytes(decode_secret("EASYEPG_SETTINGS_B64"))
    (storage / "playlist.m3u").write_bytes(decode_secret("EASYEPG_PLAYLIST_B64"))
    print("EasyEPG configuration restored from encrypted GitHub secrets")


if __name__ == "__main__":
    main()
