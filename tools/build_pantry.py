# -*- coding: utf-8 -*-
"""Build a normalised 'pantry' block (starting stock + purchases) into week.json."""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _week_path():
    if len(sys.argv) > 1:
        return os.path.join(ROOT, "weeks", sys.argv[1], "week.json")
    ids = sorted(d for d in os.listdir(os.path.join(ROOT, "weeks"))
                 if os.path.exists(os.path.join(ROOT, "weeks", d, "week.json")))
    return os.path.join(ROOT, "weeks", ids[-1], "week.json")


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
    items = {}

    def add(food, fid, qty, unit, note, src):
        fid = fid or NAME2ID.get(food) or NAME2ID.get(food.split("（")[0])
        key = fid or food
        amount, u = to_amount(qty, unit, note)
        rec = items.get(key)
        if not rec:
            rec = items[key] = {
                "foodId": key, "food": food, "unit": u,
                "base": 0.0, "tracked": True, "sources": [],
                "cat": (FOODS.get(fid) or {}).get("cat", "其他"),
            }
        rec["sources"].append(src)
        if amount is None:
            rec["tracked"] = False
            return
        if u != rec["unit"]:
            # mixed units (eg. 个 vs g): keep the first, mark untracked to stay honest
            rec["tracked"] = False
            return
        rec["base"] += amount

    for p in week.get("pantryBefore", []):
        add(p["food"], p.get("foodId"), p.get("qty"), p.get("unit"), p.get("note"), "库存")
    for b in week.get("shopping", []):
        for it in b["items"]:
            add(it["food"], it.get("foodId"), it.get("qty"), it.get("unit"), it.get("note"), b["batch"])

    out = []
    for rec in items.values():
        if rec["base"] <= 0 and rec["tracked"]:
            rec["tracked"] = False
        if rec["cat"] == "调味":
            rec["tracked"] = False
        rec.pop("sources", None)
        out.append(rec)
    out.sort(key=lambda r: (ORDER.index(r["cat"]) if r["cat"] in ORDER else 99, r["food"]))

    week["pantry"] = out
    json.dump(week, open(WEEK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    for r in out:
        print("%-4s %-8s %-6s base=%s tracked=%s" % (r["cat"], r["food"], r["unit"], r["base"], r["tracked"]))


if __name__ == "__main__":
    main()
