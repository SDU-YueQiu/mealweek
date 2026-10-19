# -*- coding: utf-8 -*-
"""Add stable dishId/foodId to the dry-run week and publish it to weeks/<id>/."""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "week-2026-W43.json")
DISHES = json.load(open(os.path.join(ROOT, "library", "dishes.json"), encoding="utf-8"))
FOODS = json.load(open(os.path.join(ROOT, "library", "foods.json"), encoding="utf-8"))

FOOD_ALIASES = {
    "米饭（生米）": "dami", "大米": "dami",
    "粉丝（干）": "fensi", "粉丝": "fensi",
    "木耳（干）": "muer", "干木耳": "muer",
    "面粉（中筋）": "mianfen", "面粉": "mianfen",
    "郫县豆瓣酱": "doubanjiang",
    "猪精瘦肉": "zhujing-shourou", "猪里脊": "zhujing-shourou",
    "卤水豆腐": "lvshui-doufu", "包浆豆腐": "lvshui-doufu",
    "上海青": "shanghai-qing", "菠菜": "bocai", "大白菜": "dabaicai",
    "青蒜": "qingsuan", "小葱": "xiaocong", "姜": "jiang", "蒜": "suan",
    "干辣椒": "ganlajiao", "花椒": "huajiao", "花椒粉": "huajiaofen",
    "食用油": "shiyongyou", "生抽": "shengchou", "老抽": "laochou",
    "蚝油": "haoyou", "料酒": "liaojiu", "淀粉": "dianfen",
    "糖": "tang", "醋": "cu", "盐": "yan", "香油": "xiangyou",
    "黑胡椒": "heihujiao", "十三香": "shisanxiang", "清水": "qingshui",
    "鸡蛋": "jidan", "鸡胸": "jixiong", "牛肉": "niurou", "牛腿肉": "niurou",
    "年糕": "niangao", "挂面": "guamian", "番茄": "fanqie",
    "青椒": "qingjiao", "黄瓜": "huanggua", "胡萝卜": "huluobo",
    "洋葱": "yangcong", "香菇": "xianggu", "花生米": "huashengmi",
    "芹菜": "qincai", "蒜苔": "suantai",
    "姜、蒜、小葱": "jiang", "干辣椒、花椒": "ganlajiao",
}

NAME_TO_DISH = {v["name"]: k for k, v in DISHES.items()}

missing_dish, missing_food = set(), set()


def food_id(name):
    if name in FOOD_ALIASES:
        return FOOD_ALIASES[name]
    simple = re.sub(r"（.*?）", "", name)
    if simple in FOOD_ALIASES:
        return FOOD_ALIASES[simple]
    missing_food.add(name)
    return None


week = json.load(open(SRC, encoding="utf-8"))

for day in week["days"]:
    for meal in day["meals"]:
        did = NAME_TO_DISH.get(meal["name"])
        if not did:
            missing_dish.add(meal["name"])
            did = re.sub(r"[^\w]+", "-", meal["name"]).strip("-")
        meal["dishId"] = did
        meal["image"] = "dish/%s.webp" % did
        for it in meal["items"]:
            it["foodId"] = food_id(it["food"])
        # keep items ordered by appearance

for batch in week["shopping"]:
    for it in batch["items"]:
        it["foodId"] = food_id(it["food"])

for p in week["pantryAfter"]:
    p["foodId"] = food_id(p["food"])

outdir = os.path.join(ROOT, "weeks", week["id"])
os.makedirs(outdir, exist_ok=True)
out = os.path.join(outdir, "week.json")
json.dump(week, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print("wrote", out)
print("missing dish ids:", sorted(missing_dish))
print("missing food ids:", sorted(missing_food))
ids = {m["dishId"] for d in week["days"] for m in d["meals"]}
print("dishes used:", len(ids))
print("foods used:", len({i["foodId"] for d in week["days"] for m in d["meals"] for i in m["items"] if i["foodId"]}))
