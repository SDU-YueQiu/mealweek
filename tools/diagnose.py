# -*- coding: utf-8 -*-
"""Fold a week's events.jsonl into a diagnosis card.

    python tools/diagnose.py [week-id]

Writes weeks/<id>/diagnosis.md and prints it.
"""
import json, os, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEEKS = os.path.join(ROOT, "weeks")


def latest_week():
    ids = [d for d in os.listdir(WEEKS) if os.path.isdir(os.path.join(WEEKS, d))]
    ids = [d for d in ids if os.path.exists(os.path.join(WEEKS, d, "week.json"))]
    return sorted(ids)[-1] if ids else None


def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def fold(events):
    meals, days, thaw, shopping, week = {}, {}, {}, {}, {}
    for e in sorted(events, key=lambda x: x.get("at", "")):
        t = e.get("type")
        if t == "meal" and e.get("date") and e.get("slot"):
            meals.setdefault((e["date"], e["slot"]), {})[e.get("field")] = e.get("value")
        elif t == "day" and e.get("date"):
            days.setdefault(e["date"], {})[e.get("field")] = e.get("value")
        elif t == "thaw":
            thaw[e.get("at")] = bool(e.get("done"))
        elif t == "shopping":
            shopping[(e.get("batch"), e.get("food"))] = bool(e.get("checked"))
        elif t == "week" and e.get("field"):
            week[e["field"]] = e.get("value")
    return meals, days, thaw, shopping, week


def avg(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 1) if vals else None


def main():
    wid = sys.argv[1] if len(sys.argv) > 1 else latest_week()
    if not wid:
        print("no week")
        return 1
    wdir = os.path.join(WEEKS, wid)
    week = json.load(open(os.path.join(wdir, "week.json"), encoding="utf-8"))
    events = read_jsonl(os.path.join(wdir, "events.jsonl"))
    meals, days, thaw, shopping, weekev = fold(events)

    name_of = {}
    for d in week["days"]:
        for m in d["meals"]:
            name_of[(d["date"], m["slot"])] = m["name"]

    # execution
    status = Counter()
    skipped = []
    for key, rec in meals.items():
        if rec.get("status"):
            status[rec["status"]] += 1
            if rec["status"] == "skipped":
                skipped.append(key)
    total_meals = sum(len(d["meals"]) for d in week["days"])
    logged = len([k for k, v in meals.items() if any(x not in (None, "", []) for x in v.values())])

    # taste
    rated = [(k, v["rating"]) for k, v in meals.items() if isinstance(v.get("rating"), (int, float))]
    ratings = [r for _, r in rated]
    bad = [name_of.get(k, k[1]) for k, r in rated if r == 1]
    good = [name_of.get(k, k[1]) for k, r in rated if r == 3]
    tags = Counter()
    for v in meals.values():
        for t in (v.get("tags") or []):
            tags[t] += 1

    # body
    hunger = {d: v.get("hunger") for d, v in days.items() if v.get("hunger")}
    energy = {d: v.get("energy") for d, v in days.items() if v.get("energy")}
    max_hunger = max(hunger.items(), key=lambda kv: kv[1])[1] if hunger else None
    worst_day = max(hunger.items(), key=lambda kv: kv[1])[0] if hunger else None

    # thaw
    thaw_total = len(thaw)
    thaw_missed = [k for k, v in thaw.items() if not v]

    # shopping
    planned_items = [(b["batch"], it["food"]) for b in week["shopping"] for it in b["items"]]
    bought = sum(1 for k in planned_items if shopping.get(k))
    missed_shopping = [k[1] for k in planned_items if shopping.get(k) is False]

    # weight
    weight = weekev.get("weight")
    prev = None
    ids = sorted([d for d in os.listdir(WEEKS) if os.path.isdir(os.path.join(WEEKS, d))])
    if wid in ids:
        idx = ids.index(wid)
        for j in range(idx - 1, -1, -1):
            ev = read_jsonl(os.path.join(WEEKS, ids[j], "events.jsonl"))
            _, _, _, _, w = fold(ev)
            if w.get("weight"):
                prev = w["weight"]
                break

    # prescriptions
    fix = []
    if tags.get("太咸", 0) >= 3:
        fix.append("太咸 %d 次：全周生抽/豆瓣 -20%%，步骤里写清楚" % tags["太咸"])
    if tags.get("太淡", 0) >= 3:
        fix.append("太淡 %d 次：加醋/辣椒/香料，别加盐" % tags["太淡"])
    if tags.get("太麻烦", 0) >= 2:
        fix.append("太麻烦 %d 次：把超过 30 分钟的菜移到周末" % tags["太麻烦"])
    if tags.get("量太大", 0) >= 2:
        fix.append("量太大 %d 次：该餐主食 -10%%" % tags["量太大"])
    if tags.get("量太少", 0) >= 2:
        fix.append("量太少 %d 次：该餐加 100 g 菜或 10 g 蛋白" % tags["量太少"])
    if bad:
        fix.append("下架 4 周：" + "、".join(sorted(set(bad))))
    slot_skip = Counter(k[1] for k in skipped)
    for slot, n in slot_skip.items():
        if n >= 2:
            fix.append("%s 跳过 %d 次：换成 15 分钟内的一锅出，或设免做饭日" % (slot, n))
    if hunger and avg(hunger.values()) and avg(hunger.values()) >= 4:
        fix.append("平均饥饿 %.1f：晚餐 +100 g 蔬菜、+10 g 蛋白，热量从午餐挪" % avg(hunger.values()))
    if len(thaw_missed) >= 2:
        fix.append("解冻忘 %d 次：提醒挪到早上出门前，或那两天改蛋/豆腐" % len(thaw_missed))
    if weight and prev and prev > 0:
        pct = (weight - prev) / prev * 100
        if pct > -0.5:
            fix.append("体重只降 %.1f%%，低于 0.5%%：下周 +100 kcal" % abs(pct))
        elif pct < -1:
            fix.append("体重降 %.1f%%，超过 1%%：下周 -100 kcal 或蛋白 +10 g" % abs(pct))

    def dish(d):
        if not d:
            return ""
        return "（%s）" % name_of.get(d, d[1])

    lines = []
    lines.append("# %s 诊断" % wid)
    lines.append("")
    lines.append("数据：%d 条事件，%d/%d 餐有反馈。" % (len(events), logged, total_meals))
    lines.append("")
    if not events:
        lines.append("这周还没有任何反馈。先在手机上勾几顿，诊断才有东西可算。")
        text = "\n".join(lines)
        print(text)
        open(os.path.join(wdir, "diagnosis.md"), "w", encoding="utf-8").write(text + "\n")
        return 0

    lines.append("| 项 | 结果 |")
    lines.append("| --- | --- |")
    lines.append("| 执行 | 照做 %d · 跳过 %d · 换了 %d |" % (status["eaten"], status["skipped"], status["swapped"]))
    if skipped:
        lines.append("| 跳过 | " + "、".join("%s %s" % (d[0][5:], d[1]) for d in skipped[:6]) + " |")
    if ratings:
        lines.append("| 口味 | 平均 %.1f / 3，评分 %d 道 |" % (avg(ratings), len(ratings)))
    if tags:
        lines.append("| 标签 | " + " · ".join("%s×%d" % (k, v) for k, v in tags.most_common(5)) + " |")
    if hunger:
        lines.append("| 饥饿 | 均值 %.1f，最高 %s（%s） |" % (avg(hunger.values()), max_hunger, worst_day))
    if energy:
        lines.append("| 精力 | 均值 %.1f |" % avg(energy.values()))
    if thaw_total:
        lines.append("| 解冻 | %d 次任务，忘 %d 次 |" % (thaw_total, len(thaw_missed)))
    lines.append("| 采购 | 已买 %d/%d |" % (bought, len(planned_items)))
    if missed_shopping:
        lines.append("| 没买到 | " + "、".join(missed_shopping[:6]) + " |")
    if weight:
        if prev:
            lines.append("| 体重 | %.1f → %.1f kg（%+.1f） |" % (prev, weight, weight - prev))
        else:
            lines.append("| 体重 | %.1f kg |" % weight)
    if bad:
        lines.append("| 不想再做 | " + "、".join(sorted(set(bad))) + " |")
    if good:
        lines.append("| 还想吃 | " + "、".join(sorted(set(good))[:8]) + " |")

    notes = []
    for k, v in meals.items():
        txt = v.get("note")
        if isinstance(txt, str) and txt.strip():
            notes.append((name_of.get(k, k[1]), txt.strip()))
    if notes:
        lines.append("")
        lines.append("## 备注")
        lines.append("")
        for name, txt in notes[:20]:
            lines.append("- **%s**：%s" % (name, txt))

    lines.append("")
    lines.append("## 下周处方")
    lines.append("")
    if fix:
        for f in fix:
            lines.append("- " + f)
    else:
        lines.append("- 没有触发任何规则，按原菜单继续。")
    lines.append("")
    text = "\n".join(lines)
    print(text)
    with open(os.path.join(wdir, "diagnosis.md"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
