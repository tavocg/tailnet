#!/usr/bin/env python3
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from html import escape, unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import ssl
from posixpath import basename
from urllib.parse import parse_qs, quote, urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


UPSTREAM_MASTER = "https://cdn01.teletica.com/TeleticaLiveStream/Stream/playlist_dvr.m3u8"
UPSTREAM_ORIGIN = "https://cdn01.teletica.com/"
SCHEDULE_URL = "https://www.teletica.com/programa"
REFERER = "https://bradmax.com/"
TLS_CONTEXT = ssl._create_unverified_context()

try:
    CR_TZ = ZoneInfo("America/Costa_Rica")
except ZoneInfoNotFoundError:
    CR_TZ = timezone(timedelta(hours=-6), "CST")


def encode_url(url):
    return urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")


def decode_url(value):
    padded = value + ("=" * (-len(value) % 4))
    return urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


def xmltv_time(dt):
    return dt.strftime("%Y%m%d%H%M%S %z")


def fetch_teletica_programs():
    request = Request(
        SCHEDULE_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=20, context=TLS_CONTEXT) as response:
        html = response.read().decode("utf-8", errors="replace")

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Teletica schedule data was not found")

    data = json.loads(unescape(match.group(1)))
    return data["props"]["pageProps"].get("programs", [])


def build_teletica_events(programs, days=8):
    today = datetime.now(CR_TZ).date()
    events = []
    for day_offset in range(-1, days):
        current_date = today + timedelta(days=day_offset)
        teletica_day = (current_date.weekday() + 1) % 7

        for program in programs:
            if 1 not in program.get("ChannelId", []):
                continue

            starts_h = program.get("InitHour", [])
            starts_m = program.get("InitMinute", [])
            ends_h = program.get("EndHour", [])
            ends_m = program.get("EndMinute", [])
            day_values = program.get("Day", [])
            count = min(len(day_values), len(starts_h), len(starts_m), len(ends_h), len(ends_m))

            for index in range(count):
                if day_values[index] != teletica_day:
                    continue

                start = datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    int(starts_h[index]),
                    int(starts_m[index]),
                    tzinfo=CR_TZ,
                )
                stop = datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    int(ends_h[index]),
                    int(ends_m[index]),
                    tzinfo=CR_TZ,
                )
                if stop <= start:
                    stop += timedelta(days=1)

                image = first_image_url(program)
                events.append(
                    {
                        "title": program.get("ProgramName", "Teletica"),
                        "start": start,
                        "stop": stop,
                        "url": program.get("NodeSlug", ""),
                        "image": image,
                    }
                )

    return sorted(events, key=lambda event: event["start"])


def first_image_url(program):
    for media in program.get("MediaSizesPaths", []):
        path = media.get("Size2Path") or media.get("Size1Path")
        if not path:
            continue
        path = path.split("?", 1)[0]
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin("https://teletica-static.ray.media/", path)
    return ""


class Handler(BaseHTTPRequestHandler):
    server_version = "TeleticaJellyfinProxy/1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/playlist.m3u":
            self.send_playlist()
        elif parsed.path == "/xmltv.xml":
            self.send_xmltv()
        elif parsed.path == "/hls" or parsed.path.startswith("/hls/"):
            self.proxy_hls(parsed)
        else:
            self.send_error(404)

    def public_base(self):
        host = self.headers.get("Host", f"127.0.0.1:{self.server.server_port}")
        return f"http://{host}"

    def send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_playlist(self):
        base = self.public_base()
        stream = self.local_hls_url(base, UPSTREAM_MASTER)
        xmltv = f"{base}/xmltv.xml"
        body = (
            '#EXTM3U x-tvg-url="{xmltv}"\n'
            '#EXTINF:-1 tvg-id="teletica" tvg-name="Teletica" tvg-chno="7" '
            'group-title="Costa Rica",Teletica\n'
            "{stream}\n"
        ).format(xmltv=xmltv, stream=stream)
        self.send_bytes(200, body.encode("utf-8"), "audio/x-mpegurl; charset=utf-8")

    def send_xmltv(self):
        try:
            events = build_teletica_events(fetch_teletica_programs())
        except Exception as exc:
            self.send_error(502, escape(str(exc)))
            return

        rows = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<tv generator-info-name="teletica-jellyfin-proxy">',
            '  <channel id="teletica">',
            "    <display-name>Teletica</display-name>",
            "    <display-name>Teletica 7</display-name>",
            "  </channel>",
        ]

        for event in events:
            rows.append(
                f'  <programme start="{xmltv_time(event["start"])}" '
                f'stop="{xmltv_time(event["stop"])}" channel="teletica">'
            )
            rows.append(f'    <title lang="es">{escape(event["title"])}</title>')
            if event["url"]:
                rows.append(f'    <category lang="es">{escape(event["url"])}</category>')
            if event["image"]:
                rows.append(f'    <icon src="{escape(event["image"], quote=True)}" />')
            rows.append("  </programme>")
        rows.append("</tv>")
        self.send_bytes(200, "\n".join(rows).encode("utf-8"), "application/xml; charset=utf-8")

    def proxy_hls(self, parsed):
        try:
            if parsed.path.startswith("/hls/"):
                encoded = basename(parsed.path).split(".", 1)[0]
            else:
                values = parse_qs(parsed.query).get("u")
                if not values:
                    self.send_error(400, "missing upstream URL")
                    return
                encoded = values[0]
            upstream_url = decode_url(encoded)
        except Exception:
            self.send_error(400, "invalid upstream URL")
            return

        if not upstream_url.startswith(UPSTREAM_ORIGIN):
            self.send_error(403, "upstream URL not allowed")
            return

        try:
            request = Request(
                upstream_url,
                headers={
                    "Referer": REFERER,
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "*/*",
                },
            )
            with urlopen(request, timeout=20, context=TLS_CONTEXT) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type", "application/octet-stream")
        except Exception as exc:
            self.send_error(502, escape(str(exc)))
            return

        if b"#EXTM3U" in body[:256]:
            body = self.rewrite_playlist(body, upstream_url)
            content_type = "application/vnd.apple.mpegurl; charset=utf-8"

        self.send_bytes(200, body, content_type)

    def rewrite_playlist(self, body, current_upstream_url):
        base = self.public_base()
        rewritten = []
        text = body.decode("utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                rewritten.append(line)
                continue

            if stripped.startswith("http://") or stripped.startswith("https://"):
                next_url = stripped
            elif stripped.startswith("TeleticaLiveStream/"):
                next_url = urljoin(UPSTREAM_ORIGIN, stripped)
            else:
                next_url = urljoin(current_upstream_url, stripped)

            rewritten.append(self.local_hls_url(base, next_url))
        return ("\n".join(rewritten) + "\n").encode("utf-8")

    def local_hls_url(self, base, upstream_url):
        extension = urlparse(upstream_url).path.rsplit(".", 1)
        suffix = f".{extension[1]}" if len(extension) == 2 else ""
        return f"{base}/hls/{quote(encode_url(upstream_url))}{suffix}"


def main():
    server = ThreadingHTTPServer(("0.0.0.0", 8787), Handler)
    print("Serving Teletica Jellyfin proxy on http://0.0.0.0:8787")
    print("M3U:   http://127.0.0.1:8787/playlist.m3u")
    print("XMLTV: http://127.0.0.1:8787/xmltv.xml")
    server.serve_forever()


if __name__ == "__main__":
    main()
