# -*- coding: utf-8 -*-
"""Macros for a list of ingredients, and a consistency check for a week file.

    python tools/nutrition.py "挂面:90,鸡蛋:3,食用油:8,生抽:5"
    python tools/nutrition.py --check weeks/2026-W45/week.json

Numbers are per 100 g (or per 100 ml) edible portion, 4/4/9 kcal.  The point is
that every meal in weeks/*/week.json is reproducible from its items list, so a
typo in a gram amount can never silently keep an old calorie total.
"""

import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# foodId -> (protein, carb, fat) per 100 g
TABLE = {
    "jixiong": (24.6, 0.6, 1.9),
    "niurou": (20.2, 1.2, 2.3),
    "zhujing-shourou": (20.3, 1.5, 6.2),
    "zhuliji": (20.2, 0.7, 7.9),
    "jidan": (13.3, 2.8, 8.8),
    "lvshui-doufu": (12.2, 1.5, 4.8),
    "baojian-doufu": (9.0, 2.0, 5.0),
    "fanqie": (0.9, 3.3, 0.2),
    "qingjiao": (1.4, 5.4, 0.3),
    "huanggua": (0.8, 2.9, 0.2),
    "huluobo": (1.0, 8.8, 0.2),
    "yangcong": (1.1, 9.0, 0.2),
    "shanghai-qing": (1.5, 2.4, 0.3),
    "bocai": (2.6, 4.5, 0.3),
    "dabaicai": (1.5, 3.2, 0.1),
    "qincai": (1.2, 4.5, 0.2),
    "suantai": (2.0, 15.4, 0.1),
    "qingsuan": (2.4, 8.1, 0.2),
    "xianggu": (2.2, 5.2, 0.3),
    "muer": (12.1, 65.6, 1.5),
    "huashengmi": (24.8, 21.7, 44.3),
    "dami": (7.4, 77.9, 0.8),
    "guamian": (11.4, 74.7, 0.9),
    "niangao": (3.3, 34.7, 0.6),
    "mianfen": (11.2, 73.6, 1.5),
    "fensi": (0.8, 83.7, 0.2),
    "doubanjiang": (13.6, 14.2, 6.8),
    "jiang": (1.3, 10.3, 0.6),
    "suan": (4.5, 27.6, 0.2),
    "xiaocong": (1.7, 6.5, 0.4),
    "ganlajiao": (15.4, 57.4, 12.0),
    "huajiao": (6.7, 66.5, 8.9),
    "huajiaofen": (6.7, 66.5, 8.9),
    "shiyongyou": (0.0, 0.0, 99.9),
    "xiangyou": (0.0, 0.2, 99.7),
    "shengchou": (5.6, 9.9, 0.1),
    "laochou": (7.0, 12.0, 0.2),
    "haoyou": (4.0, 21.0, 0.3),
    "liaojiu": (0.2, 5.0, 0.0),
    "dianfen": (1.2, 85.0, 0.1),
    "tang": (0.0, 99.9, 0.0),
    "cu": (2.1, 4.9, 0.3),
    "yan": (0.0, 0.0, 0.0),
    "heihujiao": (10.0, 64.0, 3.0),
    "shisanxiang": (10.0, 60.0, 8.0),
    "ziranfen": (8.0, 60.0, 5.0),
    "lajiaofen": (15.0, 50.0, 10.0),
    "qingshui": (0.0, 0.0, 0.0),
    # 包装背面营养成分表（每 100 g）：王中王 776 kJ / 香甜王 704 kJ / 白象面饼+调料
    "huotuichang": (12.5, 7.0, 12.0),
    "xiangtianwang": (10.0, 14.0, 8.0),
    "fangbianmian": (9.2, 51.6, 24.1),
}

# units the recipes use (片/瓣/根/个) -> grams, per food
UNIT_GRAMS = {
    "jidan": {"个": 55.0},
    "jiang": {"片": 3.0},
    "suan": {"瓣": 5.0},
    "xiaocong": {"根": 5.0},
    "ganlajiao": {"个": 1.5},
    "yancong": {"个": 200.0},
    "huotuichang": {"根": 30.0},
    "xiangtianwang": {"根": 30.0},
    "fangbianmian": {"包": 110.0},
}

NAMES = {}


def load_names():
    foods = json.load(open(os.path.join(ROOT, "library", "foods.json"), encoding="utf-8"))
    for k, v in foods.items():
        NAMES[v["name"]] = k
    NAMES.update({"牛肉": "niurou", "牛腿肉": "niurou", "豆干": "lvshui-doufu",
                  "米饭（生米）": "dami", "大米": "dami", "粉丝（干）": "fensi",
                  "木耳（干）": "muer", "鸡蛋（去壳）": "jidan"})


def grams_of(fid, qty, unit):
    unit = (unit or "g").strip()
    if unit in ("g", "克", "ml"):
        return float(qty)
    conv = UNIT_GRAMS.get(fid, {}).get(unit)
    if conv:
        return float(qty) * conv
    raise ValueError("不知道 %s 的 %s 等于多少克" % (fid, unit))


def macros(items):
    """items: [(foodId, qty, unit)] -> dict(kcal, carb, protein, fat)."""
    p = c = f = 0.0
    for fid, qty, unit in items:
        if fid not in TABLE:
            raise KeyError("没有 %s 的营养数据" % fid)
        g = grams_of(fid, qty, unit) / 100.0
        ip, ic, if_ = TABLE[fid]
        p += ip * g
        c += ic * g
        f += if_ * g
    return {"kcal": round(p * 4 + c * 4 + f * 9, 1),
            "carb": round(c, 1), "protein": round(p, 1), "fat": round(f, 1)}


def parse_spec(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        name, qty = part.split(":")
        unit = "g"
        m = re.match(r"^([\d.]+)\s*(\D*)$", qty.strip())
        if m:
            qty, unit = float(m.group(1)), (m.group(2).strip() or "g")
        out.append((NAMES.get(name, name), qty, unit))
    return out


def check(path):
    week = json.load(open(path, encoding="utf-8"))
    bad = 0
    for d in week["days"]:
        tot = {"kcal": 0.0, "carb": 0.0, "protein": 0.0, "fat": 0.0}
        line = []
        for m in d["meals"]:
            items = [(it.get("foodId"), it.get("qty"),
                      it.get("unit") or ("g" if it.get("g") else "g")) for it in m.get("items") or []]
            got = macros(items)
            for k in tot:
                tot[k] += got[k]
            keep = m.get("macros") or {}
            diff = max(abs(got[k] - keep.get(k, 0)) for k in tot)
            flag = "" if diff <= 4 else "  <<< 差 %.1f" % diff
            if diff > 4:
                bad += 1
            line.append("    %-6s %-10s %4d kcal  P%-5.1f C%-5.1f F%-5.1f%s" % (
                m["slot"], m["name"][:10], got["kcal"], got["protein"], got["carb"], got["fat"], flag))
        print("%s %s  合计 %d kcal  P%.1f C%.1f F%.1f   (文件里写 %s)" % (
            d["date"], d.get("label", ""), tot["kcal"], tot["protein"], tot["carb"], tot["fat"],
            d["totals"]))
        print("\n".join(line))
    print("不一致的餐：%d" % bad)
    return 1 if bad else 0


def main():
    load_names()
    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        return check(sys.argv[2])
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    items = parse_spec(sys.argv[1])
    m = macros(items)
    print(" ".join("%s %s%s" % (f, q, u) for f, q, u in items))
    print("  %d kcal  P %.1f  C %.1f  F %.1f" % (m["kcal"], m["protein"], m["carb"], m["fat"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
