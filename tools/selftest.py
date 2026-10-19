# -*- coding: utf-8 -*-
"""Data + endpoint self-check before shipping a week.

    python tools/selftest.py
"""
import json, os, sys, urllib.request
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEEKS = os.path.join(ROOT, "weeks")
ASSETS = os.path.join(ROOT, "assets")

ok, bad, warn = [], [], []


def check(cond, msg, soft=False):
    (ok if cond else (warn if soft else bad)).append(msg)


def main():
    ids = sorted(d for d in os.listdir(WEEKS) if os.path.isdir(os.path.join(WEEKS, d)))
    check(bool(ids), "weeks/ 下至少有一个周目录")
    if not ids:
        return report()
    wid = ids[-1]
    wdir = os.path.join(WEEKS, wid)
    week = json.load(open(os.path.join(wdir, "week.json"), encoding="utf-8"))
    dishes = json.load(open(os.path.join(ROOT, "library", "dishes.json"), encoding="utf-8"))
    foods = json.load(open(os.path.join(ROOT, "library", "foods.json"), encoding="utf-8"))

    check(week.get("id") == wid, "week.id 与目录名一致 (%s)" % wid)
    days = week.get("days") or []
    check(len(days) >= 1, "至少 1 天")
    t = week["targets"]
    rng = t["range"]

    dish_ids, food_ids = set(), set()
    for d in days:
        check(len(d["meals"]) == 3, "%s 三餐齐全" % d["date"])
        for k in ("kcal", "carb", "protein", "fat"):
            s = round(sum(m["macros"][k] for m in d["meals"]), 1)
            check(abs(s - d["totals"][k]) <= 0.15, "%s %s 合计 %.1f = 三餐和 %.1f" % (d["date"], k, d["totals"][k], s))
        for k in ("kcal", "carb", "protein", "fat"):
            v = d["totals"][k]
            lo, hi = rng[k]
            check(lo <= v <= hi, "%s %s %.1f 在 %s–%s" % (d["date"], k, v, lo, hi), soft=True)
        for m in d["meals"]:
            check(bool(m.get("dishId")), "%s %s 有 dishId" % (d["date"], m["slot"]))
            check(m["dishId"] in dishes, "dishId %s 在注册表里" % m.get("dishId"))
            check(len(m.get("steps") or []) >= 3, "%s %s 步骤 >= 3" % (d["date"], m["slot"]))
            check(bool(m.get("tip")), "%s %s 有提示" % (d["date"], m["slot"]), soft=True)
            for it in m.get("items") or []:
                fid = it.get("foodId")
                check(bool(fid), "%s %s 食材 %s 有 foodId" % (d["date"], m["slot"], it.get("food")))
                if fid:
                    food_ids.add(fid)
                    check(fid in foods, "foodId %s 在注册表里" % fid)
            dish_ids.add(m["dishId"])

    for b in week.get("shopping") or []:
        check(bool(b.get("items")), "%s 有采购项" % b.get("batch"))
        for it in b["items"]:
            check(bool(it.get("foodId")), "采购项 %s 有 foodId" % it.get("food"))

    ev = os.path.join(wdir, "events.jsonl")
    if os.path.exists(ev):
        n = 0
        with open(ev, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    json.loads(line)
                    n += 1
        check(True, "events.jsonl 可解析（%d 条）" % n)
    else:
        check(True, "还没有 events.jsonl（干净的一周）")

    try:
        credits = json.load(open(os.path.join(ASSETS, "credits.json"), encoding="utf-8"))
    except Exception:
        credits = {}
    no_photo = {k for k, v in credits.items() if (v or {}).get("source") in ("composite", "none", "placeholder")}
    missing_dish = [d for d in dish_ids
                    if d not in no_photo and not os.path.exists(os.path.join(ASSETS, "dish", d + ".webp"))]
    missing_food = [f for f in food_ids
                    if f not in no_photo and not os.path.exists(os.path.join(ASSETS, "food", f + ".webp"))]
    check(not missing_dish, "缺少菜图：%s" % (missing_dish or "无"))
    check(not missing_food, "缺少食材图：%s" % (missing_food or "无"), soft=True)

    # http
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=3) as r:
            check(r.status == 200, "服务在 8765 上响应")
        with urllib.request.urlopen("http://127.0.0.1:8765/api/week", timeout=5) as r:
            payload = json.load(r)
            check(payload["week"]["id"] == wid, "/api/week 返回最新周 %s" % wid)
            real = [d for d in dish_ids if d not in no_photo]
            check(sorted(payload.get("assets", {}).get("dish", {})) == sorted(real),
                  "菜图清单 %d 项（无照片的 %d 道走品类卡）" % (len(real), len(dish_ids) - len(real)))
    except Exception as e:
        warn.append("服务未运行（跳过 HTTP 检查）：%s" % str(e)[:60])

    return report()


def report():
    for m in ok:
        print("  PASS  " + m)
    for m in warn:
        print("  WARN  " + m)
    for m in bad:
        print("  FAIL  " + m)
    print()
    print("%d passed, %d warnings, %d failed" % (len(ok), len(warn), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
