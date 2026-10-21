# -*- coding: utf-8 -*-
"""Build a standalone offline HTML pack from the latest week.

    python tools/build_offline.py [out.html]

The result embeds the app, the week JSON, and every image it needs as data
URIs.  Open it from a phone's Downloads folder; no server or certificate.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import server  # noqa: E402


def main():
    week, wd = server.load_week()
    if not week:
        print("没有周数据：先放 weeks/<id>/week.json")
        return 1
    base = "http://%s:8765" % server.lan_ip()
    html = server.build_offline_html(week, wd, base)
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "dist", "mealweek-%s.html" % week["id"])
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(html)
    print("wrote %s (%.1f MB)" % (out, len(html) / 1048576.0))
    print("sync base:", base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
