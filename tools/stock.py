# -*- coding: utf-8 -*-
"""Print what the 冰箱 page shows right now, by replaying events.jsonl.

    python tools/stock.py [week-id]

Same rules as web/app.js: a pantry row is the sum of its parts (the "before"
stock plus every shopping batch whose checkbox is ticked), minus everything in
meals already marked eaten, unless the phone stored an explicit amount
(`pantry` event) for that food.
"""

import json, os, sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIT_GRAMS = {"jiang": {"片": 3}, "suan": {"瓣": 5}, "xiaocong": {"根": 5}, "ganlajiao": {"个": 1.5}}


def week_dir(wid=None):
    base = os.path.join(ROOT, "weeks")
    if wid:
        return os.path.join(base, wid)
    import re
    ids = sorted(d for d in os.listdir(base) if os.path.exists(os.path.join(base, d, "week.json")))
    dated = [d for d in ids if re.match(r"^\d{4}-W\d{2}$", d)]
    return os.path.join(base, (dated or ids)[-1])


def replay(wdir):
    week = json.load(open(os.path.join(wdir, "week.json"), encoding="utf-8"))
    data = {"meals": {}, "shopping": {}, "pantry": {}}
    ev_path = os.path.join(wdir, "events.jsonl")
    evs = []
    if os.path.exists(ev_path):
        for line in open(ev_path, encoding="utf-8"):
            if line.strip():
                evs.append(json.loads(line))
    for e in sorted(evs, key=lambda x: str(x.get("at") or "")):
        t = e.get("type")
        if t == "meal":
            data["meals"]["%s|%s" % (e.get("date"), e.get("slot"))] = {e.get("field"): e.get("value")}
        elif t == "shopping":
            data["shopping"]["%s|%s" % (e.get("batch"), e.get("food"))] = bool(e.get("checked"))
        elif t == "pantry":
            data["pantry"][e.get("foodId")] = float(e.get("value") or 0)
    return week, data


def stock_rows(week, data):
    out = []
    for p in week.get("pantry") or []:
        if not p.get("tracked"):
            continue
        parts = p.get("parts") or [{"src": "before", "qty": p.get("base") or 0,
                                    "unit": p.get("unit"), "food": p.get("food")}]
        bought = 0.0
        for q in parts:
            if q.get("src") != "before" and not data["shopping"].get(q["src"] + "|" + (q.get("food") or "")):
                continue
            if q.get("unit") and q.get("unit") != p["unit"]:
                continue
            bought += float(q.get("qty") or 0)
        used = 0.0
        for d in week.get("days") or []:
            for m in d.get("meals") or []:
                rec = data["meals"].get("%s|%s" % (d["date"], m["slot"])) or {}
                if rec.get("status") != "eaten":
                    continue
                for it in m.get("items") or []:
                    if it.get("foodId") != p["foodId"]:
                        continue
                    q = float(it.get("qty") or 0)
                    if not q:
                        continue
                    if it.get("unit") == p["unit"]:
                        used += q
                    elif p["unit"] == "g" and it.get("unit") in ("g", "ml"):
                        used += q
                    elif p["unit"] == "g":
                        used += q * UNIT_GRAMS.get(p["foodId"], {}).get(it.get("unit"), 0)
        auto = max(0.0, bought - used)
        shown = data["pantry"].get(p["foodId"])
        shown = auto if shown is None else shown
        out.append({
            "food": p["food"], "foodId": p["foodId"], "cat": p.get("cat"), "unit": p["unit"],
            "bought": bought, "used": used, "shown": shown,
            "state": p.get("state"), "expireAt": p.get("expireAt"),
        })
    return out


def main():
    wdir = week_dir(sys.argv[1] if len(sys.argv) > 1 else None)
    week, data = replay(wdir)
    rows = stock_rows(week, data)
    print("# %s  今天 %s" % (week.get("id"), date.today().isoformat()))
    for r in sorted(rows, key=lambda r: (r["cat"] or "", r["food"])):
        if r["shown"] <= 0 and r["bought"] <= 0:
            continue
        print("%-4s %-8s %6.0f %-2s 买%6.0f 吃%6.0f  %s %s" % (
            r["cat"] or "", r["food"], r["shown"], r["unit"], r["bought"], r["used"],
            r["state"] or "", r["expireAt"] or ""))


if __name__ == "__main__":
    main()
