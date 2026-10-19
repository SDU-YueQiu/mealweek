# -*- coding: utf-8 -*-
"""Fetch images from Wikimedia Commons (search + strict title filter),
compose placeholders, and build a contact sheet for review."""
import io, json, os, re, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISH_DIR = os.path.join(ROOT, "assets", "dish")
FOOD_DIR = os.path.join(ROOT, "assets", "food")
PREV = os.path.join(ROOT, "assets", "_preview")
UA = "MealWeekPlanner/0.1 (personal cooking planner; iop18@example.com)"
CM = "https://commons.wikimedia.org/w/api.php"

# id: (search query, required substring in file title)
SPEC = {
    "fanqie": ("tomato vegetable", "tomato"),
    "qingjiao": ("green bell pepper vegetable", "pepper"),
    "huanggua": ("cucumber vegetable", "cucumber"),
    "huluobo": ("carrot vegetable", "carrot"),
    "yangcong": ("onion vegetable", "onion"),
    "xianggu": ("shiitake mushroom", "shiitake"),
    "qingsuan": ("garlic sprout", "garlic"),
    "guamian": ("dried noodles bundle", "noodle"),
    "jiang": ("ginger rhizome", "ginger"),
    "xiaocong": ("spring onion", "onion"),
    "qincai": ("celery stalks", "celery"),
    "huajiao": ("sichuan peppercorns", "peppercorn"),
    "muer": ("wood ear fungus", "wood ear"),
    "lvshui-doufu": ("tofu block", "tofu"),
    "suantai": ("garlic scapes", "scape"),
    "ganlajiao": ("dried red chili peppers", "chili"),
    "bocai": ("spinach leaves", "spinach"),
    "shanghai-qing": ("pak choi", "choi"),
    "huashengmi": ("peanut", "peanut"),
    "fensi": ("glass noodles", "noodle"),
    "muer": ("wood ear mushroom", "wood ear"),
    "dabaicai": ("napa cabbage", "cabbage"),
    "suantai": ("garlic scape", "scape"),
    "qincai": ("celery", "celery"),
    "jidan": ("chicken egg", "egg"),
    "jixiong": ("raw chicken breast", "chicken"),
    "niurou": ("beef steak raw", "beef"),
    "zhujing-shourou": ("pork loin", "pork"),
    "lvshui-doufu": ("tofu block", "tofu"),
    "dami": ("white rice grains", "rice"),
    "guamian": ("dried noodles", "noodle"),
    "niangao": ("nian gao rice cake", "nian gao"),
    "mianfen": ("wheat flour", "flour"),
    "doubanjiang": ("doubanjiang", "doubanjiang"),
    "shanghai-qing": ("bok choy", "choy"),
    "bocai": ("spinach leaves", "spinach"),
    "xiaocong": ("scallion", "scallion"),
    "suan": ("garlic bulb", "garlic"),
    "jiang": ("ginger root", "ginger"),
    "ganlajiao": ("dried chili pepper", "chili"),
    "huajiao": ("sichuan pepper", "pepper"),
    "gongbao-jiding": ("kung pao chicken", "kung pao"),
    "mapo-doufu": ("mapo tofu", "mapo"),
    "yuxiang-rousi": ("yuxiang shredded pork", "yuxiang"),
    "dan-chaofan": ("egg fried rice", "fried rice"),
    "xianggu-niurou-mian": ("beef noodle soup", "beef noodle"),
    "fanqie-roupian-danhua": ("egg drop soup", "egg"),
}

FOOD_MAIN = {
    "fanqie-jidan-mian": "fanqie", "bocai-jisi-tangmian": "bocai",
    "bocai-jidan-mian": "bocai", "qingjiao-jiding": "qingjiao",
    "heijiao-niuliu": "niurou", "fanqie-niurou-tang": "fanqie",
    "qingjiao-rousi": "qingjiao", "baicai-doufu-bao": "dabaicai",
    "qincai-rousi": "qincai", "baicai-zhurou-fentiao": "dabaicai",
    "niangao-tang": "niangao", "suantai-rousi": "suantai",
    "xianggu-roupian": "xianggu", "huluobo-jidan-bing": "huluobo",
    "gongbao-jiding": "jixiong", "mapo-doufu": "lvshui-doufu",
    "yuxiang-rousi": "zhujing-shourou", "dan-chaofan": "jidan",
    "xianggu-niurou-mian": "niurou", "fanqie-roupian-danhua": "fanqie",
}

BAD = re.compile(r"(logo|map\b|diagram|sign\b|menu|poster|chart|graph|cover\b|stamp|coin|"
                 r"factory|gate\b|portrait|painting|sculpture|no\.\s?\d+|museum|"
                 r"rice roll|bread|cake|oil|pickle|band\b|concert|stage|wild|forest|"
                 r"packet|label|package|advert)", re.I)


def get_json(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:
            time.sleep(2 + i * 2)
    return None


def search(query, need, limit=8):
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "formatversion": "2",
        "generator": "search", "gsrsearch": query, "gsrnamespace": "6",
        "gsrlimit": str(limit), "prop": "imageinfo",
        "iiprop": "url|size", "iiurlwidth": "1000",
    })
    d = get_json(CM + "?" + q)
    if not d or "query" not in d:
        return None
    pages = sorted(d["query"]["pages"], key=lambda p: p.get("index", 99))
    for p in pages:
        title = p["title"]
        if not re.search(r"\.(jpe?g|png)$", title, re.I):
            continue
        if need.lower() not in title.lower():
            continue
        if BAD.search(title):
            continue
        info = (p.get("imageinfo") or [{}])[0]
        if info.get("width", 0) < 600:
            continue
        return {"title": title, "url": info.get("thumburl"), "page": info.get("descriptionurl")}
    return None


def fetch_bytes(url):
    req = urllib.request.Request(url.split("?")[0], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def crop(im, ratio):
    w, h = im.size
    if w / h > ratio:
        nw = int(h * ratio)
        im = im.crop(((w - nw) // 2, 0, (w + nw) // 2, h))
    else:
        nh = int(w / ratio)
        top = max(0, int((h - nh) * 0.4))
        im = im.crop((0, top, w, top + nh))
    return im


def to_webp(raw, dest, ratio, width):
    from PIL import Image
    im = crop(Image.open(io.BytesIO(raw)).convert("RGB"), ratio)
    h = int(width * im.size[1] / im.size[0])
    im.resize((width, h), Image.LANCZOS).save(dest, "WEBP", quality=82, method=6)


FONTS = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simhei.ttf"]


def font(size):
    from PIL import ImageFont
    for p in FONTS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def compose(dest, label, food_path, ratio, width):
    from PIL import Image, ImageDraw, ImageFilter
    h = int(width / ratio)
    if food_path and os.path.exists(food_path):
        base = crop(Image.open(food_path).convert("RGB"), ratio).resize((width, h), Image.LANCZOS)
        base = base.filter(ImageFilter.GaussianBlur(6))
        canvas = Image.blend(base, Image.new("RGB", base.size, (28, 22, 18)), 0.42)
    else:
        canvas = Image.new("RGB", (width, h), (128, 98, 74))
    d = ImageDraw.Draw(canvas)
    f = font(int(width / (9 if len(label) > 4 else 7.6)))
    bbox = d.textbbox((0, 0), label, font=f)
    tw = bbox[2] - bbox[0]
    d.text(((width - tw) / 2 + 1, (h - bbox[3]) / 2 + 2), label, font=f, fill=(0, 0, 0))
    d.text(((width - tw) / 2, (h - bbox[3]) / 2), label, font=f, fill=(255, 248, 238))
    canvas.save(dest, "WEBP", quality=84, method=6)


def build_sheet(food_ids, dish_ids):
    from PIL import Image, ImageDraw
    os.makedirs(PREV, exist_ok=True)
    cell, cols = 190, 6
    items = []
    for fid in food_ids:
        items.append(("food/" + fid, os.path.join(FOOD_DIR, fid + ".webp")))
    for did in dish_ids:
        items.append(("dish/" + did, os.path.join(DISH_DIR, did + ".webp")))
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 20)), (250, 246, 238))
    d = ImageDraw.Draw(sheet)
    f = font(12)
    for i, (name, path) in enumerate(items):
        x, y = (i % cols) * cell, (i // cols) * (cell + 20)
        if os.path.exists(path):
            im = Image.open(path).convert("RGB").resize((cell - 6, cell - 6))
            sheet.paste(im, (x + 3, y + 3))
        d.text((x + 3, y + cell - 2), name[:26], font=f, fill=(40, 34, 28))
    out = os.path.join(PREV, "sheet.png")
    sheet.save(out)
    print("sheet:", out, sheet.size)


def compose_dish(dest, label, food_path, ratio, width):
    """Dish stand-in: main-ingredient photo with a dark foot and a 示意图 tag."""
    from PIL import Image, ImageDraw
    h = int(width / ratio)
    if food_path and os.path.exists(food_path):
        base = crop(Image.open(food_path).convert("RGB"), ratio).resize((width, h), Image.LANCZOS).convert("RGBA")
        overlay = Image.new("RGBA", (width, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        start = int(h * 0.55)
        for y in range(start, h):
            t = (y - start) / max(1, h - start)
            od.line([(0, y), (width, y)], fill=(16, 11, 8, int(150 * t * t)))
        canvas = Image.alpha_composite(base, overlay).convert("RGB")
    else:
        canvas = Image.new("RGB", (width, h), (128, 98, 74))
    d = ImageDraw.Draw(canvas)
    f = font(16)
    txt = "示意图"
    b = d.textbbox((0, 0), txt, font=f)
    tw, th = b[2] - b[0], b[3] - b[1]
    d.rounded_rectangle([width - tw - 26, h - th - 22, width - 10, h - 10], 9, fill=(255, 250, 244))
    d.text((width - tw - 18, h - th - 17), txt, font=f, fill=(60, 48, 38))
    canvas.save(dest, "WEBP", quality=84, method=6)


def main():
    week = json.load(open(os.path.join(ROOT, "weeks", "2026-W43", "week.json"), encoding="utf-8"))
    dish_ids = []
    for d in week["days"]:
        for m in d["meals"]:
            if m["dishId"] not in dish_ids:
                dish_ids.append(m["dishId"])
    food_ids = []
    for d in week["days"]:
        for m in d["meals"]:
            for it in m["items"]:
                fid = it.get("foodId")
                if fid and fid not in food_ids:
                    food_ids.append(fid)

    credits_path = os.path.join(ROOT, "assets", "credits.json")
    credits = json.load(open(credits_path, encoding="utf-8")) if os.path.exists(credits_path) else {}
    os.makedirs(FOOD_DIR, exist_ok=True)
    os.makedirs(DISH_DIR, exist_ok=True)

    for kind, ids in (("food", food_ids), ("dish", dish_ids)):
        for i, fid in enumerate(ids):
            dest = os.path.join(FOOD_DIR if kind == "food" else DISH_DIR, fid + ".webp")
            if os.path.exists(dest):
                continue
            spec = SPEC.get(fid)
            hit = None
            if spec:
                hit = search(spec[0], spec[1])
                time.sleep(0.4)
            if hit and hit.get("url"):
                try:
                    to_webp(fetch_bytes(hit["url"]), dest, 1.0 if kind == "food" else 4 / 3,
                            480 if kind == "food" else 720)
                    credits[fid] = {"source": "commons", "title": hit["title"],
                                    "url": hit["url"].split("?")[0], "page": hit["page"]}
                    print("ok  ", kind, fid, "<-", hit["title"][:60])
                    continue
                except Exception as e:
                    print("fail", kind, fid, str(e)[:60])
            credits[fid] = credits.get(fid) or {"source": "pending"}
            print("miss", kind, fid)

    # placeholders: food by name, dish by main ingredient
    names = {}
    for lib, key in (("foods.json", "food"), ("dishes.json", "dish")):
        data = json.load(open(os.path.join(ROOT, "library", lib), encoding="utf-8"))
        names.update({k: v["name"] for k, v in data.items()})
    for fid in food_ids:
        dest = os.path.join(FOOD_DIR, fid + ".webp")
        if not os.path.exists(dest):
            compose(dest, names.get(fid, fid), None, 1.0, 480)
            credits[fid] = {"source": "placeholder"}
    for did in dish_ids:
        dest = os.path.join(DISH_DIR, did + ".webp")
        if not os.path.exists(dest):
            main = FOOD_MAIN.get(did)
            compose_dish(dest, names.get(did, did), os.path.join(FOOD_DIR, main + ".webp") if main else None, 16 / 9, 1280)
            credits[did] = {"source": "composite", "base": main}

    json.dump(credits, open(credits_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    build_sheet(food_ids, dish_ids)
    print("done")


if __name__ == "__main__":
    main()
