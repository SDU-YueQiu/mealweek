# -*- coding: utf-8 -*-
"""Fetch one dish photo from Wikimedia Commons and register it.

    python tools/fetch_one.py ji-dan-tang-mian "egg noodle soup" noodle

Writes assets/dish/<id>.webp (1280x720) and adds an entry to credits.json with
source "commons", so tools/selftest.py accepts the dish as having a real photo.
"""

import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_images import search, fetch_bytes, to_webp, ROOT, DISH_DIR, FOOD_DIR  # noqa: E402

CREDITS = os.path.join(ROOT, "assets", "credits.json")
TRAIN_DIR = os.path.join(ROOT, "assets", "train")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    food = "--food" in sys.argv
    train = "--train" in sys.argv
    if len(args) < 2:
        print(__doc__)
        return 2
    dish_id, query = args[0], args[1]
    need = args[2] if len(args) > 2 else ""
    hit = search(query, need, limit=12)
    if not hit:
        print("NO MATCH:", query)
        return 1
    raw = fetch_bytes(hit["url"])
    dest_dir = TRAIN_DIR if train else (FOOD_DIR if food else DISH_DIR)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, dish_id + ".webp")
    to_webp(raw, dest, 16 / 9.0, 1280)
    credits = {}
    if os.path.exists(CREDITS):
        credits = json.load(open(CREDITS, encoding="utf-8"))
    prefix = "train/" if train else ("food/" if food else "")
    credits[prefix + dish_id] = {
        "source": "commons", "title": hit["title"],
        "url": hit["url"], "page": hit["page"]}
    json.dump(credits, open(CREDITS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("OK", dish_id, hit["title"], os.path.getsize(dest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
