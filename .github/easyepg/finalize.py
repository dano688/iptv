import argparse
from collections import Counter
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    args = parser.parse_args()

    source = Path(args.source)
    target = Path(args.target)
    tree = ET.parse(source)
    root = tree.getroot()
    channels = root.findall("channel")
    programmes = root.findall("programme")
    if len(channels) < 20 or len(programmes) < 1000:
        raise RuntimeError(
            f"EPG validation failed: {len(channels)} channels, {len(programmes)} programmes"
        )

    channel_ids = {channel.get("id") for channel in channels}
    unknown = [p.get("channel") for p in programmes if p.get("channel") not in channel_ids]
    if unknown:
        raise RuntimeError(f"EPG contains programmes for unknown channel {unknown[0]}")

    starts = Counter((p.get("channel"), p.get("start")) for p in programmes)
    duplicates = [key for key, count in starts.items() if count > 1]
    if duplicates:
        raise RuntimeError(f"EPG contains {len(duplicates)} duplicate channel/start pairs")

    normalized = 0
    for title in root.findall("programme/title"):
        if title.text and ("«" in title.text or "»" in title.text):
            title.text = title.text.replace("«", "").replace("»", "").strip()
            normalized += 1

    temporary = target.with_suffix(".tmp")
    ET.indent(root, space="  ")
    tree.write(temporary, encoding="utf-8", xml_declaration=True)
    ET.parse(temporary)
    shutil.move(temporary, target)
    print(
        f"Validated {len(channels)} channels and {len(programmes)} programmes; "
        f"normalized {normalized} titles"
    )


if __name__ == "__main__":
    main()
