#!/usr/bin/env python3
"""
build-walkthrough-plan.py — generate a people-showcase walkthrough plan.

Reads consolidated.json and emits a content-card deck (plan.json) for
walkthrough-recorder.mjs: not a tour of the dashboard, but a produced showcase of
what the team actually said — the week's topic + video, big attributed pull-quotes
whose narration reads the person's own words, theme montages featuring many
voices, a couple of graph cards, the recommendations, and a whole-team names
montage so everyone is seen.

The narration here is a strong default; the record-walkthrough skill may refine it.

Usage:
  python3 build-walkthrough-plan.py <consolidated.json> --out <plan.json>
"""

import argparse
import json
import re


EMOJI = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F000-\U0001F0FF"
    "\U00002190-\U000021FF" "\U00002B00-\U00002BFF" "️‍" "]+", flags=re.UNICODE)


def sanitize(text, maxlen=300):
    if not text:
        return ""
    t = re.sub(r"https?://\S+", "", str(text))
    t = EMOJI.sub("", t)
    t = re.sub(r"^\s*\d+[.)]\s*", "", t)            # leading "1. "
    t = re.sub(r"\s+", " ", t).strip().strip('"').strip()
    if len(t) > maxlen:
        cut = t[:maxlen]
        dot = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        t = (cut[:dot + 1] if dot > 80 else cut.rstrip() + "…")
    return t.strip()


def words(text):
    return len(re.findall(r"\S+", text or ""))


def collect_quotes(c):
    """Pool attributed quotes from every source, sanitized, dedup by person+text."""
    pool = []
    seen = set()
    photos = c.get("photos") or {}

    def add(name, text, question, kind="quote"):
        name = (name or "").strip()
        text = sanitize(text)
        if not name or not text or words(text) < 5:
            return
        key = (name.lower(), text[:50].lower())
        if key in seen:
            return
        seen.add(key)
        pool.append({"name": name, "text": text, "question": sanitize(question, 140),
                     "kind": kind, "photo": photos.get(name)})

    for s in c.get("standoutResponses") or []:
        add(s.get("name") or s.get("respondent"), s.get("response") or s.get("text"), s.get("question"), "standout")
    for q in c.get("notableQuotes") or []:
        add(q.get("name") or q.get("respondent"), q.get("text"), q.get("question"), "notable")
    for t in c.get("themes") or []:
        for q in t.get("allQuotes") or []:
            add(q.get("name") or q.get("respondent"), q.get("text"), q.get("question") or t.get("name"), "theme")
    for fq in c.get("freeTextQuestions") or []:
        for r in fq.get("responses") or []:
            add(r.get("respondent"), r.get("text"), fq.get("text"), "free")
    return pool


def best_per_person(pool):
    """One strongest quote per person (longest substantive), preserving source priority."""
    rank = {"standout": 0, "notable": 1, "theme": 2, "free": 3}
    by = {}
    for q in pool:
        cur = by.get(q["name"])
        if cur is None or (rank[q["kind"]], -words(q["text"])) < (rank[cur["kind"]], -words(cur["text"])):
            by[q["name"]] = q
    return by


def gist(text):
    """First sentence — the bit to highlight on the card + paraphrase in the voice."""
    s = re.split(r"(?<=[.!?])\s", (text or "").strip())[0]
    return s.strip()


def quote_card(q, lead=None):
    text = q["text"]
    g = gist(text)
    lead = lead or f"{q['name']} made the point that —"
    # Default narration is a SEED: name + the key sentence. The record-walkthrough
    # skill refines this into a proper paraphrase (don't read the whole quote
    # verbatim). The card shows the full quote with the key phrase highlighted.
    return {
        "kind": "quote", "quote": text, "name": q["name"], "photo": q.get("photo"),
        "context": q.get("question") or "",
        "highlight": (g if (g and g != text and len(g) < len(text)) else None),
        "narration": f"{lead} {g}",
    }


def montage_card(heading, quotes, narr_lead):
    shown = quotes[:4]
    names = ", ".join(q["name"] for q in shown[:3]) + (", and more" if len(quotes) > 3 else "")
    return {
        "kind": "montage", "heading": heading,
        "quotes": [{"text": sanitize(q["text"], 150), "name": q["name"], "photo": q.get("photo")} for q in shown],
        "narration": f"{narr_lead} {names} all had something to add.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("consolidated")
    ap.add_argument("--url", default=None, help="(unused for content cards; kept for compatibility)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    c = json.load(open(args.consolidated, encoding="utf-8"))
    meta = c.get("metadata") or {}
    topic = (meta.get("topic") or meta.get("surveyName") or "this week's topic").strip()
    topic_q = topic.rstrip("?")
    n = meta.get("responseCount") or 0
    date = meta.get("dateRange") or ""
    video = meta.get("videoWatched") or {}
    qbreak = c.get("questionBreakdown") or []
    metrics = c.get("keyMetrics") or []
    recs = c.get("recommendations") or {}
    redflags = c.get("redFlags") or []
    people = (c.get("people") or {}).get("respondents") or []
    so = c.get("sentimentOverview") or {}

    ratings = [q for q in qbreak if q.get("kind") == "rating" and q.get("mean") is not None]
    def rating_mean(*kw):
        for q in ratings:
            tl = (q.get("text") or "").lower()
            if any(k in tl for k in kw):
                return q.get("mean")
        return None
    video_mean = rating_mean("video")
    rule_mean = rating_mean("rule")
    task_mean = rating_mean("task", "value of this week")
    top_pick = next((m.get("value") for m in metrics if m.get("label") in ("Top pick", "Favourite CLI", "Favourite tool")), None)

    pool = collect_quotes(c)
    by_person = best_per_person(pool)
    # contrarian / honest-feedback quotes: skeptic voices + critique language
    crit_re = re.compile(r"\b(but|not great|left field|why|isn't|wasn't|stuck|lock|loop|struggl|confus|non-?dev|missing|wrong|disappoint)\b", re.I)
    honest = [q for q in by_person.values() if crit_re.search(q["text"])]
    honest.sort(key=lambda q: -words(q["text"]))
    honest_names = {q["name"] for q in honest[:4]}
    wins = [q for q in by_person.values() if q["name"] not in honest_names]
    wins.sort(key=lambda q: (0 if q["kind"] in ("standout", "notable") else 1, -words(q["text"])))

    chapters = []

    # intro
    chapters.append({
        "kind": "intro", "title": topic, "subtitle": f"{n} responses · {date}".strip(" ·"),
        "agenda": ["What the team said", "Where it wins", "The honest feedback", "What's next"],
        "narration": (
            f"This week's Chewing the Fat asked the team a simple question: {topic_q.lower()}? "
            f"{n} people answered — and they had a lot to say. Let's hear it from them."
        ),
    })

    # topic + video
    chapters.append({
        "kind": "topic", "title": topic,
        "video": video,
        "ratings": [r for r in [
            {"label": "video", "value": video_mean} if video_mean else None,
            {"label": "rule", "value": rule_mean} if rule_mean else None,
            {"label": "task", "value": task_mean} if task_mean else None,
        ] if r],
        "narration": (
            (f"This week we watched {video.get('title')!r}" + (f", which the team rated {video_mean} out of five. " if video_mean else ". "))
            if video.get("title") else "First, the setup. "
        ) + (f"Then everyone read the rule — it scored {rule_mean} out of five. So, broad agreement. But the good stuff is in the detail." if rule_mean else ""),
    })

    # headline stat
    if top_pick:
        chapters.append({
            "kind": "stat", "eyebrow": "The daily driver", "big": top_pick,
            "label": "the runaway favourite", "sub": "But which tool matters less than how the team is using it.",
            "narration": f"One clear winner up front: {top_pick} is the team's daily-driver favourite. Now — how are people actually using these tools?",
        })

    # section: where it wins
    chapters.append({"kind": "section", "eyebrow": "In their words", "title": "Where it wins",
                     "subtitle": "The team's real experiences with AI on the command line.",
                     "narration": "Here's where people found it genuinely better."})
    win_leads = ["{n} found that", "{n} put it this way.", "For {n},", "{n} said,", "{n}'s experience:"]
    for i, q in enumerate(wins[:5]):
        lead = win_leads[i % len(win_leads)].format(n=q["name"])
        chapters.append(quote_card(q, lead))

    # a montage of more voices
    extra_wins = wins[5:9]
    if extra_wins:
        chapters.append(montage_card("More wins from the team", extra_wins, "And it wasn't just them —"))

    # graph: ratings
    if ratings:
        chapters.append({
            "kind": "graph", "eyebrow": "By the numbers", "title": "How the ratings landed",
            "chartType": "bar",
            "labels": [(q.get("text") or "")[:22] for q in ratings],
            "data": [q.get("mean") for q in ratings],
            "caption": "Out of 5 — strong across the board, no low scores.",
            "narration": "By the numbers, the ratings were strong across the board — fours and fives, almost no low scores.",
        })

    # graph: tool tally
    choice = next((q for q in qbreak if q.get("kind") in ("multi-select", "single-select") and q.get("distribution")), None)
    if choice:
        items = sorted(choice["distribution"].items(), key=lambda kv: kv[1], reverse=True)[:6]
        chapters.append({
            "kind": "graph", "eyebrow": "By the numbers", "title": "What the team is actually using",
            "chartType": "bar", "horizontal": True,
            "labels": [k for k, _ in items], "data": [v for _, v in items],
            "caption": sanitize(choice.get("text"), 80),
            "narration": "And here's what people are actually reaching for, day to day.",
        })

    # section: honest feedback
    chapters.append({"kind": "section", "eyebrow": "Keeping it real", "title": "The honest feedback",
                     "subtitle": "The contrarians, the gripes, and the fair points worth hearing.",
                     "narration": "Now — the honest feedback. The best surveys have people pushing back, and this one did."})
    honest_leads = ["{n} pushed back:", "{n} wasn't sold:", "{n} raised a fair point.", "{n} kept it real:"]
    for i, q in enumerate(honest[:4]):
        chapters.append(quote_card(q, honest_leads[i % len(honest_leads)].format(n=q["name"])))

    # section: what's next
    rec_items = []
    for tier, label in [("immediate", "This week"), ("shortTerm", "This quarter"), ("strategic", "Longer term")]:
        for r in (recs.get(tier) or [])[:1]:
            rec_items.append({"tag": label, "title": sanitize(r.get("action"), 120), "sub": sanitize(r.get("rationale"), 120)})
    if rec_items:
        chapters.append({
            "kind": "list", "eyebrow": "What's next", "title": "What SSW should do",
            "items": rec_items,
            "narration": (
                "So what do we do with all this? "
                + " ".join(f"{it['tag']}: {it['title'].rstrip('.')}." for it in rec_items)
            ),
        })

    # whole-team names montage — everyone is seen
    names = sorted({p.get("name") for p in people if p.get("name")})
    if names:
        chapters.append({
            "kind": "names", "eyebrow": "The whole team", "title": "Everyone who weighed in",
            "subtitle": f"{len(names)} people took the time to share what they think.",
            "names": names,
            "narration": f"And that's the team — all {len(names)} of you who took the time to share what you think. Every voice here shaped the picture. Thank you.",
        })

    # outro
    chapters.append({
        "kind": "outro", "title": "That's this week", "subtitle": topic,
        "recap": ["Heard from the team", "Saw where it wins", "Took the honest feedback", "Know what's next"],
        "narration": "That's this week's Chewing the Fat. The full dashboard has every question and every answer if you want to dig in. See you next week.",
    })

    plan = {"survey": topic, "date": date, "accent": "#CC4141", "chapters": chapters}
    json.dump(plan, open(args.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    feat = len([ch for ch in chapters if ch["kind"] == "quote"])
    print(f"[build-walkthrough-plan] wrote {args.out}: {len(chapters)} cards, "
          f"{feat} featured quotes, {len(names)} people in the montage")


if __name__ == "__main__":
    main()
