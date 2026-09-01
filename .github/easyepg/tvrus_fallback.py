import argparse
from datetime import date, datetime, time as datetime_time, timedelta, timezone, tzinfo
from html.parser import HTMLParser
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


SOURCES = {
    "tv-rus": "https://www.tvrus.eu/tv-programm_2025lu/",
    "tv-rus-plus": "https://www.tvrus.eu/tv-programm-plus_2025da/",
}
LOOKAHEAD_DAYS = 2


class ScheduleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.date_by_tab = {}
        self.entries = []
        self.anchor = None
        self.anchor_text = []
        self.tab_depth = 0
        self.tab_date = None
        self.programme_depth = 0
        self.programme_text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set(attributes.get("class", "").split())
        if tag == "a" and attributes.get("href", "").startswith("#"):
            self.anchor = attributes["href"][1:]
            self.anchor_text = []
        if tag == "div":
            if self.tab_depth:
                self.tab_depth += 1
            elif "tvtab" in classes:
                self.tab_depth = 1
                self.tab_date = self.date_by_tab.get(attributes.get("id"))
        if tag == "p" and self.tab_depth and "tvlist" in classes:
            self.programme_depth = 1
            self.programme_text = []
        elif self.programme_depth:
            self.programme_depth += 1

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            try:
                self.date_by_tab[self.anchor] = datetime.strptime(
                    "".join(self.anchor_text).strip(), "%d.%m.%Y"
                ).date()
            except ValueError:
                pass
            self.anchor = None
            self.anchor_text = []
        if self.programme_depth:
            self.programme_depth -= 1
            if self.programme_depth == 0 and tag == "p" and self.tab_date:
                text = " ".join("".join(self.programme_text).split())
                match = re.match(r"^(\d{1,2}:\d{2})\s+(.+)$", text)
                if match:
                    self.entries.append((self.tab_date, match.group(1), match.group(2)))
                self.programme_text = []
        if tag == "div" and self.tab_depth:
            self.tab_depth -= 1
            if self.tab_depth == 0:
                self.tab_date = None

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor_text.append(data)
        if self.programme_depth:
            self.programme_text.append(data)


def last_sunday(year, month):
    following = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last_day = following - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() + 1) % 7)


class EuropeBerlinFallback(tzinfo):
    def _dst(self, value):
        local = value.replace(tzinfo=None)
        start = datetime.combine(last_sunday(value.year, 3), datetime_time(2))
        end = datetime.combine(last_sunday(value.year, 10), datetime_time(3))
        return start <= local < end

    def utcoffset(self, value):
        return timedelta(hours=2 if self._dst(value) else 1)

    def dst(self, value):
        return timedelta(hours=1 if self._dst(value) else 0)

    def tzname(self, value):
        return "CEST" if self._dst(value) else "CET"

    def fromutc(self, value):
        plain = value.replace(tzinfo=None)
        start = datetime.combine(last_sunday(plain.year, 3), datetime_time(1))
        end = datetime.combine(last_sunday(plain.year, 10), datetime_time(1))
        hours = 2 if start <= plain < end else 1
        return (plain + timedelta(hours=hours)).replace(tzinfo=self)


def berlin_timezone():
    if ZoneInfo:
        try:
            return ZoneInfo("Europe/Berlin")
        except Exception:
            pass
    return EuropeBerlinFallback()


def parse_xmltv_time(value):
    match = re.match(r"^(\d{14})(?:\s*([+-]\d{4}))?", value or "")
    if not match:
        return None
    return datetime.strptime(
        match.group(1) + " " + (match.group(2) or "+0000"), "%Y%m%d%H%M%S %z"
    )


def xmltv_utc(value):
    return value.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")


def fetch_schedule(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="replace")
    parser = ScheduleParser()
    parser.feed(html)
    if not parser.entries:
        raise ValueError("no programmes found on the official TVRUS page")

    zone = berlin_timezone()
    programmes = []
    previous_clock = None
    previous_date = None
    rollover = 0
    for tab_date, clock_text, title in parser.entries:
        if tab_date != previous_date:
            previous_clock = None
            previous_date = tab_date
            rollover = 0
        clock = datetime.strptime(clock_text, "%H:%M").time()
        if previous_clock is not None and clock < previous_clock:
            rollover += 1
        start = datetime.combine(
            tab_date + timedelta(days=rollover), datetime_time(clock.hour, clock.minute)
        ).replace(tzinfo=zone)
        programmes.append({"start": start, "title": title})
        previous_clock = clock
    programmes.sort(key=lambda item: item["start"])
    for index, programme in enumerate(programmes):
        programme["stop"] = (
            programmes[index + 1]["start"]
            if index + 1 < len(programmes)
            else programme["start"] + timedelta(minutes=60)
        )
    return programmes


def existing_coverage(xml_path, channel_ids, zone):
    starts = {channel_id: set() for channel_id in channel_ids}
    dates = {channel_id: set() for channel_id in channel_ids}
    for _, element in ET.iterparse(xml_path, events=("end",)):
        if element.tag == "programme" and element.get("channel") in starts:
            parsed = parse_xmltv_time(element.get("start"))
            if parsed:
                channel_id = element.get("channel")
                starts[channel_id].add(parsed.astimezone(timezone.utc))
                dates[channel_id].add(parsed.astimezone(zone).date())
        element.clear()
    return starts, dates


def programme_xml(channel_id, programme):
    element = ET.Element(
        "programme",
        {
            "start": xmltv_utc(programme["start"]),
            "stop": xmltv_utc(programme["stop"]),
            "channel": channel_id,
        },
    )
    ET.SubElement(element, "title", {"lang": "ru"}).text = programme["title"]
    return ET.tostring(element, encoding="unicode", short_empty_elements=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xml")
    args = parser.parse_args()
    zone = berlin_timezone()
    today = datetime.now(zone).date()
    required = today + timedelta(days=LOOKAHEAD_DAYS)
    starts, dates = existing_coverage(args.xml, SOURCES, zone)
    additions = []

    for channel_id, url in SOURCES.items():
        latest = max(dates[channel_id], default=None)
        if latest and latest >= required:
            print(f"{channel_id}: IPTVX already reaches {latest}; fallback skipped")
            continue
        print(f"{channel_id}: IPTVX is short; checking official TVRUS schedule")
        official = fetch_schedule(url)
        official_dates = {item["start"].date() for item in official}
        if required not in official_dates:
            raise RuntimeError(f"{channel_id}: official schedule does not reach {required}")
        missing_dates = {
            item_date for item_date in official_dates
            if item_date >= today and item_date not in dates[channel_id]
        }
        count = 0
        for programme in official:
            start = programme["start"].astimezone(timezone.utc)
            if programme["start"].date() in missing_dates and start not in starts[channel_id]:
                additions.append(programme_xml(channel_id, programme))
                starts[channel_id].add(start)
                count += 1
        print(f"{channel_id}: prepared {count} programmes for missing whole days")

    if not additions:
        print("TVRUS fallback: nothing added")
        return
    with open(args.xml, encoding="utf-8") as source:
        xml = source.read()
    position = xml.rfind("</tv>")
    if position < 0:
        raise RuntimeError("EPG has no closing </tv> element")
    result = xml[:position].rstrip() + "\n" + "\n".join(additions) + "\n" + xml[position:]
    temporary = args.xml + ".tvrus.tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as target:
        target.write(result)
    ET.parse(temporary)
    os.replace(temporary, args.xml)
    print(f"TVRUS fallback: added {len(additions)} programmes")


if __name__ == "__main__":
    main()
