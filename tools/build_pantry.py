# -*- coding: utf-8 -*-
"""Build a normalised 'pantry' block (starting stock + purchases) into week.json.

Each tracked item also gets a storage state and an estimated eat-by date:
  state         冷冻 / 冷藏 / 常温
  stockedAt     date it entered the pantry
  shelfLifeDays days from stocking to the eat-by date
  shelfLife     human label from the source ("6 个月", "13 天")
  expireAt      ISO date, earliest of all sources

    python tools/build_pantry.py [week-id]
"""
import json, os, re, sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _week_path():
    if len(sys.argv) > 1:
        return os.path.join(ROOT, "weeks", sys.argv[1], "week.json")
    ids = sorted(d for d in os.listdir(os.path.join(ROOT, "weeks"))
                 if os.path.exists(os.path.join(ROOT, "weeks", d, "week.json")))
    dated = [d for d in ids if re.match(r"^\d{4}-W\d{2}$", d)]
    return os.path.join(ROOT, "weeks", (dated or ids)[-1], "week.json")


WEEK = _week_path()
FOODS = json.load(open(os.path.join(ROOT, "library", "foods.json"), encoding="utf-8"))

NAME2ID = {v["name"]: k for k, v in FOODS.items()}
NAME2ID.update({
    "牛腿肉": "niurou", "猪精瘦肉": "zhujing-shourou", "猪里脊": "zhuliji",
    "面粉（中筋）": "mianfen", "干木耳": "muer", "木耳（干）": "muer",
    "姜、蒜、小葱": "jiang", "干辣椒、花椒": "ganlajiao",
    "包浆豆腐": "baojian-doufu", "面粉": "mianfen",
})

ORDER = ["肉", "蛋", "豆", "蔬菜", "菌菇", "主食", "干货", "坚果", "调味", "其他"]

# Default storage life (days) when the week data has no explicit expireAt /
# shelfLife.  Fresh items in shopping usually carry expireAt, so this mostly
# covers initial stock and dry goods.
SHELF_DAYS = {
    "niurou": 180, "zhujing-shourou": 180, "zhuliji": 180, "jixiong": 180,
    "jidan": 30,
    "lvshui-doufu": 5, "baojian-doufu": 90,
    "fanqie": 7, "qingjiao": 7, "huanggua": 5, "huluobo": 14,
    "yangcong": 30, "xianggu": 5, "qingsuan": 7, "shanghai-qing": 5,
    "bocai": 5, "dabaicai": 14, "qincai": 5, "suantai": 7,
    "dami": 365, "niangao": 30, "guamian": 365, "mianfen": 180,
    "muer": 365, "fensi": 365, "huashengmi": 90,
    "jiang": 21, "xiaocong": 7, "suan": 60,
    "ganlajiao": 365, "doubanjiang": 180,
}
CAT_DAYS = {"肉": 180, "蛋": 30, "豆": 5, "蔬菜": 7, "菌菇": 5,
            "主食": 365, "干货": 365, "坚果": 90, "调味": 180, "其他": 30}
STATE_OVERRIDE = {"jiang": "冷藏", "xiaocong": "冷藏", "suan": "常温",
                  "doubanjiang": "冷藏"}


def parse_shelf_days(text):
    """'12 个月' -> 360, '2 周' -> 14, '1 年' -> 365."""
    if not text:
        return None
    m = re.search(r"(\d+)\s*(天|日|周|个月|月|年)", str(text))
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit in ("天", "日"):
        return n
    if unit == "周":
        return n * 7
    if unit in ("个月", "月"):
        return n * 30
    if unit == "年":
        return n * 365
    return None


def human_days(days):
    if days is None:
        return ""
    if days >= 365 and days % 365 == 0:
        return "%d 年" % (days // 365)
    if days >= 30 and days % 30 == 0:
        return "%d 个月" % (days // 30)
    if days >= 7 and days % 7 == 0:
        return "%d 周" % (days // 7)
    return "%d 天" % days


def guess_state(cat):
    if cat == "肉":
        return "冷冻"
    if cat in ("蛋", "豆", "蔬菜", "菌菇"):
        return "冷藏"
    return "常温"


def to_amount(qty, unit, note):
    """Return (amount, unit) where unit is g or 个/根/..."""
    if qty in (None, ""):
        return None, unit
    qty = float(qty)
    note = note or ""
    unit = (unit or "").strip()
    m = re.search(r"约?\s*([\d.]+)\s*(kg|g|克)", note)
    if unit in ("g", "克"):
        return qty, "g"
    if unit == "kg":
        return qty * 1000, "g"
    if unit in ("ml",):
        return qty, "g"
    if m:
        v = float(m.group(1))
        return (v * 1000 if m.group(2) == "kg" else v), "g"
    return qty, unit


def main():
    week = json.load(open(WEEK, encoding="utf-8"))
    week_start = date.fromisoformat(week.get("start") or date.today().isoformat())
    items = {}

    def add(food, fid, qty, unit, note, state=None, expire_at=None,
            shelf_life=None, when=None, src="before"):
        fid = fid or NAME2ID.get(food) or NAME2ID.get(food.split("（")[0])
        key = fid or food
        amount, u = to_amount(qty, unit, note)
        cat = (FOODS.get(fid) or {}).get("cat", "其他")
        rec = items.get(key)
        if not rec:
            rec = items[key] = {
                "foodId": key, "food": food, "unit": u,
                "base": 0.0, "tracked": True, "cat": cat,
                "_expiry": [], "_states": [], "_days": [], "_labels": [], "_stocked": [],
                "_parts": [],
            }
        base_date = when or week_start
        storage = state or STATE_OVERRIDE.get(fid) or guess_state(rec["cat"])

        days = parse_shelf_days(shelf_life)
        if days is None:
            days = SHELF_DAYS.get(fid)
        if days is None:
            days = CAT_DAYS.get(rec["cat"], 30)

        exp = base_date + timedelta(days=days)
        if expire_at:
            try:
                explicit = date.fromisoformat(str(expire_at)[:10])
                exp = explicit
                days = max(0, (explicit - base_date).days)
            except ValueError:
                pass

        rec["_expiry"].append(exp)
        rec["_states"].append(storage)
        rec["_days"].append(days)
        rec["_labels"].append(shelf_life or human_days(days))
        rec["_stocked"].append(base_date)

        if amount is None:
            rec["tracked"] = False
            return
        if u != rec["unit"]:
            # mixed units (eg. 个 vs g): keep the first, mark untracked to stay honest
            rec["tracked"] = False
            return
        rec["base"] += amount
        if amount > 0:
            # One row per purchase so the phone can tell what was actually
            # bought (采购一/二 checkboxes) from what is still on the list.
            rec["_parts"].append({
                "src": src, "food": food, "qty": amount, "unit": u,
                "at": base_date.isoformat(), "expireAt": exp.isoformat(),
            })

    for p in week.get("pantryBefore", []):
        add(p["food"], p.get("foodId"), p.get("qty"), p.get("unit"), p.get("note"),
            state=p.get("state"), expire_at=p.get("expireAt"),
            shelf_life=p.get("shelfLife"), when=week_start)
    for b in week.get("shopping", []):
        when = b.get("when")
        batch_date = date.fromisoformat(when[:10]) if when else week_start
        for it in b["items"]:
            add(it["food"], it.get("foodId"), it.get("qty"), it.get("unit"), it.get("note"),
                expire_at=it.get("expireAt"), shelf_life=it.get("shelfLife"),
                when=batch_date, src=b["batch"])

    out = []
    for rec in items.values():
        if rec["base"] <= 0 and rec["tracked"]:
            rec["tracked"] = False

        exps = rec.pop("_expiry")
        states = rec.pop("_states")
        dayss = rec.pop("_days")
        labels = rec.pop("_labels")
        stocked = rec.pop("_stocked")
        parts = rec.pop("_parts")
        rec["parts"] = sorted(parts, key=lambda x: (x["at"], x["src"]))
        if exps:
            win = min(range(len(exps)), key=lambda i: exps[i])
            rec["state"] = " / ".join(dict.fromkeys(states))
            rec["expireAt"] = exps[win].isoformat()
            rec["shelfLifeDays"] = dayss[win]
            rec["shelfLife"] = labels[win]
            rec["stockedAt"] = stocked[win].isoformat()
        else:
            rec["state"] = states[0] if states else guess_state(rec["cat"])
            rec["expireAt"] = None
            rec["shelfLifeDays"] = None
            rec["shelfLife"] = ""
            rec["stockedAt"] = None
        out.append(rec)

    out.sort(key=lambda r: (ORDER.index(r["cat"]) if r["cat"] in ORDER else 99, r["food"]))

    week["pantry"] = out
    json.dump(week, open(WEEK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    for r in out:
        print("%-4s %-8s %-4s base=%-7s %-5s %-10s %s" % (
            r["cat"], r["food"], r["unit"], r["base"], r["state"],
            r["expireAt"] or "-", r["shelfLife"] or "-"))


if __name__ == "__main__":
    main()
