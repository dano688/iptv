import argparse
from pathlib import Path


OLD_SETUP = '''    dt_now = datetime.now()
    dt_start = datetime(dt_now.year, dt_now.month, dt_now.day, 6, 0).timestamp()
    dt_end = (datetime(dt_now.year, dt_now.month, dt_now.day, 5, 59) + timedelta(days=int(settings["days"]))).timestamp()

'''
OLD_CONDITION = '        if g["c_id"] in channels and dt_start <= g["start"] <= dt_end:'
NEW_CONDITION = '        if g["c_id"] in channels:'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("provider")
    args = parser.parse_args()

    path = Path(args.provider)
    source = path.read_text(encoding="utf-8")
    if OLD_SETUP not in source or source.count(OLD_CONDITION) != 1:
        raise RuntimeError("Pinned EasyEPG XMLTV provider has an unexpected structure")
    source = source.replace(OLD_SETUP, "", 1).replace(OLD_CONDITION, NEW_CONDITION, 1)
    path.write_text(source, encoding="utf-8", newline="\n")
    print("EasyEPG will preserve the complete time range supplied by IPTVX")


if __name__ == "__main__":
    main()
