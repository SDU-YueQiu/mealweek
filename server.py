# -*- coding: utf-8 -*-
"""Meal-week server: static PWA + tiny JSON API. Stdlib only.

    python server.py [port]

GET  /                 web app
GET  /api/week         current week + asset hash manifest
GET  /api/events       all events of a week
POST /api/events       append events (deduplicated by id)
GET  /api/assets/...   image binaries
"""
import base64, hashlib, json, os, re, socket, ssl, sys, threading, time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
ASSETS = os.path.join(ROOT, "assets")
WEEKS = os.path.join(ROOT, "weeks")
TOKEN = os.environ.get("MW_TOKEN", "").strip()
CST = timezone(timedelta(hours=8))

MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg",
    ".svg": "image/svg+xml", ".webmanifest": "application/manifest+json",
    ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8",
}

_hash_cache = {}
_events_cache = {}
_lock = threading.Lock()


def now_iso():
    return datetime.now(CST).isoformat(timespec="seconds")


def sha1_file(path):
    st = os.stat(path)
    key = (path, st.st_mtime, st.st_size)
    if key in _hash_cache:
        return _hash_cache[key]
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    _hash_cache[key] = h.hexdigest()[:12]
    return _hash_cache[key]


def latest_week_dir():
    if not os.path.isdir(WEEKS):
        return None
    cands = [d for d in os.listdir(WEEKS)
             if os.path.isdir(os.path.join(WEEKS, d))
             and os.path.exists(os.path.join(WEEKS, d, "week.json"))]
    if not cands:
        return None
    dated = [d for d in cands if re.match(r"^\d{4}-W\d{2}$", d)]
    return os.path.join(WEEKS, sorted(dated or cands)[-1])


def week_dir(wid=None):
    """A specific week folder when it exists, otherwise the latest one."""
    wid = str(wid) if wid else ""
    if wid and wid not in (".", "..") and not wid.startswith(".") and re.match(r"^[A-Za-z0-9._-]+$", wid):
        d = os.path.join(WEEKS, wid)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "week.json")):
            return d
    return latest_week_dir()


def load_week(wid=None):
    d = week_dir(wid)
    if not d:
        return None, None
    with open(os.path.join(d, "week.json"), encoding="utf-8") as f:
        return json.load(f), d


def asset_manifest():
    man = {"dish": {}, "food": {}}
    for kind in ("dish", "food"):
        folder = os.path.join(ASSETS, kind)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if not name.endswith(".webp"):
                continue
            p = os.path.join(folder, name)
            man[kind][name[:-5]] = sha1_file(p)
    return man


def placeholder_ids(man):
    """Ids without a real photo: text placeholders and composed stand-ins."""
    p = os.path.join(ASSETS, "credits.json")
    try:
        cred = json.load(open(p, encoding="utf-8"))
    except Exception:
        return {"food": [], "dish": []}
    try:
        dishes = set(json.load(open(os.path.join(ROOT, "library", "dishes.json"), encoding="utf-8")))
    except Exception:
        dishes = set()
    out = {"food": [], "dish": []}
    for fid, meta in cred.items():
        if (meta or {}).get("source") in ("placeholder", "composite", "none"):
            out["dish" if fid in dishes else "food"].append(fid)
    return out


def read_events(week_dir):
    p = os.path.join(week_dir, "events.jsonl")
    st = os.stat(p) if os.path.exists(p) else None
    key = (p, st.st_mtime if st else 0, st.st_size if st else 0)
    if key in _events_cache:
        return _events_cache[key]
    events, ids = [], set()
    if st:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("id") in ids:
                    continue
                ids.add(e.get("id"))
                events.append(e)
    _events_cache[key] = (events, ids)
    return events, ids


def append_events(week_dir, incoming):
    events, ids = read_events(week_dir)
    added = 0
    path = os.path.join(week_dir, "events.jsonl")
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            for e in incoming:
                if not isinstance(e, dict):
                    continue
                eid = e.get("id")
                if not eid or eid in ids:
                    continue
                e["receivedAt"] = now_iso()
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
                ids.add(eid)
                added += 1
    return added


def used_asset_ids(week):
    """Only the dish/food ids this week can actually show."""
    dish, food = set(), set()
    for d in week.get("days") or []:
        for m in d.get("meals") or []:
            if m.get("dishId"):
                dish.add(m["dishId"])
            for it in m.get("items") or []:
                if it.get("foodId"):
                    food.add(it["foodId"])
    for b in week.get("shopping") or []:
        for it in b.get("items") or []:
            if it.get("foodId"):
                food.add(it["foodId"])
    for p in week.get("pantry") or []:
        if p.get("foodId"):
            food.add(p["foodId"])
    return {"dish": dish, "food": food}


def offline_assets(week, man):
    """Filter the manifest to this week, skipping text/composite placeholders."""
    used = used_asset_ids(week)
    placeholder = placeholder_ids(man)
    out = {"dish": {}, "food": {}}
    for kind in ("dish", "food"):
        skip = set(placeholder.get(kind) or [])
        for fid in sorted(used[kind]):
            h = (man.get(kind) or {}).get(fid)
            if h and fid not in skip:
                out[kind][fid] = h
    return out


def build_offline_html(week, wd, base_url):
    """One self-contained HTML: app + week data + every image it needs.

    No service worker, no HTTP server, no certificate.  Open it from the
    phone's file manager and it keeps working with the PC off.
    """
    man = asset_manifest()
    assets = offline_assets(week, man)
    events, _ = read_events(wd)
    payload = {
        "week": week,
        "assets": assets,
        "placeholder": placeholder_ids(man),
        "events": events,
        "serverBase": base_url,
        "generatedAt": now_iso(),
        "serverTime": now_iso(),
        "images": {},
    }
    for kind in ("dish", "food"):
        for fid, h in assets[kind].items():
            p = os.path.join(ASSETS, kind, fid + ".webp")
            if not os.path.isfile(p):
                continue
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            key = "/assets/%s/%s.webp?v=%s" % (kind, quote(fid, safe=""), h)
            payload["images"][key] = "data:image/webp;base64," + b64

    with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
        html = f.read()
    with open(os.path.join(WEB, "style.css"), encoding="utf-8") as f:
        css = f.read()
    with open(os.path.join(WEB, "app.js"), encoding="utf-8") as f:
        js = f.read()

    # The standalone file has no origin to resolve these against.
    html = re.sub(r'[ \t]*<link rel="manifest"[^>]*>\s*\n?', "", html)
    icon = os.path.join(ASSETS, "icon-192.png")
    if os.path.isfile(icon):
        with open(icon, "rb") as f:
            icon_uri = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
        html = html.replace('href="/assets/icon-192.png"', 'href="%s"' % icon_uri)
    if '<link rel="stylesheet" href="/style.css" />' not in html:
        raise RuntimeError("index.html 里的 style.css 引用变了，离线包模板需要更新")
    html = html.replace('<link rel="stylesheet" href="/style.css" />',
                        "<style>\n%s\n</style>" % css)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    inline = (
        "<script>window.MW_OFFLINE=%s;</script>\n"
        "<script>\n%s\n</script>" % (data, js.replace("</script", "<\\/script"))
    )
    if '<script src="/app.js"></script>' not in html:
        raise RuntimeError("index.html 里的 app.js 引用变了，离线包模板需要更新")
    html = html.replace('<script src="/app.js"></script>', inline)
    html = "<!-- MealWeek offline pack: %s, %s -->\n%s" % (week.get("id"), now_iso(), html)
    return html.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "MealWeek/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _cors_headers(self):
        # The standalone offline file lives on file:// (Origin: null) and
        # talks back to this LAN server when the phone is on the same wifi.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Token")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", cache="no-store", cors=False):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        if cors:
            self._cors_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), cache="no-store", cors=True)

    def _offline(self):
        week, wd = load_week()
        if not week:
            return self._send(404, "还没有周计划", "text/plain; charset=utf-8")
        host = (self.headers.get("Host") or "").strip()
        scheme = getattr(self.server, "scheme", "http")
        if not host or host.startswith(("127.", "localhost", "[::1]")):
            host = "%s:%d" % (lan_ip(), self.server.server_address[1])
        base = "%s://%s" % (scheme, host)
        try:
            body = build_offline_html(week, wd, base)
        except Exception as e:
            return self._send(500, "离线包生成失败：%s" % e, "text/plain; charset=utf-8")
        fn = "mealweek-%s.html" % week["id"]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % fn)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self):
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            return self._send(404, "not found", "text/plain; charset=utf-8")
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _safe_file(self, base, rel):
        p = os.path.abspath(os.path.join(base, rel.lstrip("/\\")))
        if not p.startswith(os.path.abspath(base) + os.sep):
            return None
        return p if os.path.isfile(p) else None

    def _static(self, path):
        if path in ("/", "/index.html"):
            p = os.path.join(WEB, "index.html")
            rel = "index.html"
        elif path.startswith("/assets/"):
            p = self._safe_file(ASSETS, path[len("/assets/"):])
            rel = path
        else:
            p = self._safe_file(WEB, path)
            rel = path
        if not p:
            self._send(404, "not found", "text/plain; charset=utf-8")
            return
        ext = os.path.splitext(p)[1].lower()
        ctype = MIME.get(ext, "application/octet-stream")
        cache = "public, max-age=31536000, immutable" if path.startswith("/assets/") else "no-cache"
        with open(p, "rb") as f:
            self._send(200, f.read(), ctype, cache)

    def do_GET(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        qs = parse_qs(u.query)
        if path == "/api/week":
            wid = (qs.get("week") or [None])[0]
            week, wd = load_week(wid)
            if not week or (wid and week.get("id") != wid):
                return self._json({"error": "no week"}, 404)
            man = asset_manifest()
            return self._json({"week": week, "assets": man,
                               "placeholder": placeholder_ids(man),
                               "serverTime": now_iso()})
        if path == "/api/events":
            wid = (qs.get("week") or [None])[0]
            week, wd = load_week(wid)
            if not wd or (wid and week.get("id") != wid):
                return self._json({"error": "no week"}, 404)
            events, _ = read_events(wd)
            return self._json({"week": week["id"], "events": events})
        if path == "/api/health":
            return self._json({"ok": True, "time": now_iso(), "token": bool(TOKEN)})
        if path in ("/offline", "/offline.html", "/mealweek.html"):
            return self._offline()
        if path == "/ca.pem":
            p = os.path.join(ROOT, "certs", "rootCA.pem")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    return self._send(200, f.read(), "application/x-pem-file", "no-store")
            return self._send(404, "no CA here", "text/plain; charset=utf-8")
        if path == "/ca.crt":
            p = os.path.join(ROOT, "certs", "rootCA.crt")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    return self._send(200, f.read(), "application/x-x509-ca-cert", "no-store")
            return self._send(404, "no CA here", "text/plain; charset=utf-8")
        if path in ("/setup", "/setup.html"):
            p = os.path.join(WEB, "setup.html")
            with open(p, "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8", "no-store")
        return self._static(path)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/events":
            return self._send(404, "not found", "text/plain; charset=utf-8")
        if TOKEN and self.headers.get("X-Token") != TOKEN:
            return self._json({"error": "forbidden"}, 403)
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            return self._json({"error": "bad json: %s" % e}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "body must be an object"}, 400)
        requested = body.get("week")
        week, wd = load_week(requested)
        if not wd or (requested and week.get("id") != requested):
            return self._json({"error": "no week"}, 404)
        incoming = body.get("events") or []
        if not isinstance(incoming, list):
            return self._json({"error": "events must be a list"}, 400)
        added = append_events(wd, incoming)
        events, _ = read_events(wd)
        return self._json({"ok": True, "week": week["id"], "accepted": added, "total": len(events)})


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    args = sys.argv[1:]
    cert = key = None
    if "--cert" in args:
        i = args.index("--cert")
        cert = args[i + 1]
        del args[i:i + 2]
    if "--key" in args:
        i = args.index("--key")
        key = args[i + 1]
        del args[i:i + 2]
    port = int(args[0]) if args else 8765
    also_http = 0
    if "--also-http" in args:
        i = args.index("--also-http")
        also_http = int(args[i + 1])
        del args[i:i + 2]

    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    except OSError as e:
        print("端口 %d 起不来：%s" % (port, e))
        print("换一个端口：python server.py 8766")
        return 1
    scheme = "http"
    if cert and key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        scheme = "https"
    srv.scheme = scheme
    if also_http:
        try:
            boot = ThreadingHTTPServer(("0.0.0.0", also_http), Handler)
            boot.scheme = "http"
            threading.Thread(target=boot.serve_forever, daemon=True).start()
            print("  setup : http://%s:%d/setup  （手机装证书用）" % (lan_ip(), also_http))
            print("  offline: http://%s:%d/offline.html  （不装证书也能用）" % (lan_ip(), also_http))
        except OSError as e:
            print("  引导端口 %d 起不来：%s" % (also_http, e))
    print("serving %s" % ROOT)
    print("  local : %s://127.0.0.1:%d/" % (scheme, port))
    print("  phone : %s://%s:%d/" % (scheme, lan_ip(), port))
    print("  offline: %s://%s:%d/offline.html  （下载到手机，不装证书也能用）" % (scheme, lan_ip(), port))
    print("  token : %s" % ("on" if TOKEN else "off"))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
