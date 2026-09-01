import argparse
import os
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--storage", required=True)
    parser.add_argument("--timeout", type=int, default=1500)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    storage = Path(args.storage).resolve()
    storage.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(source))

    from resources.lib import db, epg

    paths = {"included": str(source) + os.sep, "storage": str(storage) + os.sep}
    user_data = db.UserData(paths)
    user_data.main["settings"]["ag"] = "no"
    user_data.main["settings"]["rate"] = "0"

    providers = db.ProviderManager(paths, user_data)
    grabber = epg.Grabber(paths, providers, user_data)
    grabber.grabbing = True
    deadline = time.monotonic() + args.timeout
    started = False
    try:
        while time.monotonic() < deadline:
            started = started or grabber.started
            if started and not grabber.started and not grabber.grabbing:
                break
            time.sleep(0.5)
        else:
            grabber.cancellation = True
            providers.cancellation = True
            raise TimeoutError("EasyEPG generation timed out")
    finally:
        grabber.exit = True
        grabber.thread.join(timeout=15)

    output = storage / "xml" / "epg.xml"
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("EasyEPG did not create xml/epg.xml")
    if grabber.warning:
        log = storage / "grabber_error_log.txt"
        details = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        raise RuntimeError("EasyEPG completed with provider warnings\n" + details[-8000:])
    print(f"Created {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
