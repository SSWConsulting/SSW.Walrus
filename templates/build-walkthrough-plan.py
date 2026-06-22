#!/usr/bin/env python3
"""
build-walkthrough-plan.py — generate a walkthrough plan from consolidated.json.

Emits a plan.json (chapters + beats + default narration) that
walkthrough-recorder.mjs consumes to record a narrated dashboard tour. The beats
drive the real dashboard tabs; the narration is a decent PO-facing default
derived from the digest that the record-walkthrough skill refines for polish.

Usage:
  python3 build-walkthrough-plan.py <consolidated.json> --url <dashboard-url> --out <plan.json>
"""

import argparse
import json
import re


def first_sentence(text, maxlen=220):
    if not text:
        return ""
    s = re.split(r"(?<=[.!?])\s", text.strip())[0]
    return s[:maxlen]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("consolidated")
    ap.add_argument("--url", required=True, help="deployed dashboard URL or file:// path to index.html")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    c = json.load(open(args.consolidated, encoding="utf-8"))
    meta = c.get("metadata") or {}
    topic = meta.get("topic") or meta.get("surveyName") or "this week's topic"
    n = meta.get("responseCount") or 0
    date = meta.get("dateRange") or ""
    exec_sum = c.get("executiveSummary") or {}
    grade = c.get("overallGrade") or ""
    verdict = exec_sum.get("overallVerdict") or ""
    metrics = c.get("keyMetrics") or []
    qbreak = c.get("questionBreakdown") or []
    themes = c.get("themes") or []
    so = c.get("sentimentOverview") or {}
    notable = c.get("notableQuotes") or []
    recs = c.get("recommendations") or {}
    redflags = c.get("redFlags") or []
    gaps = c.get("adoptionGaps") or []

    # headline numbers
    ratings = [q for q in qbreak if q.get("kind") == "rating" and q.get("mean") is not None]
    rule_q = next((q for q in ratings if "rule" in (q.get("text", "").lower())), ratings[0] if ratings else None)
    top_pick = next((m.get("value") for m in metrics if m.get("label") in ("Top pick", "Favourite CLI", "Favourite tool")), None)
    metric_blurb = "; ".join(f"{m.get('label')} {m.get('value')}" for m in metrics[:3])

    chapter_titles = ["The verdict", "How it scored", "What the team said", "What SSW should do"]

    chapters = []

    # ----- intro -----
    chapters.append({
        "kind": "intro",
        "title": topic,
        "subtitle": f"{n} responses · {date}".strip(" ·"),
        "agenda": chapter_titles,
        "narration": (
            f"This week's Free Lunch poll asked the team about {topic.rstrip('?')}. "
            f"{n} people answered. In the next couple of minutes: the verdict, how it scored, "
            f"what the team said in their own words, and what we should do next."
        ),
    })

    # ----- ch1: verdict (Overview) -----
    ch1_beats = [
        {"action": "goto", "value": args.url},
        {"action": "clickTab", "value": "Overview"},
        {"action": "spotlight", "target": "text~:Executive Summary", "ms": 2600},
        {"action": "scrollTo", "target": "text~:Overall Verdict"},
        {"action": "spotlight", "target": "text~:Overall Verdict", "ms": 2400},
    ]
    chapters.append({
        "kind": "chapter", "number": 1, "title": "The verdict", "section": "Overview",
        "dividerText": "The headline result and the few things that matter.",
        "beats": ch1_beats,
        "narration": (
            f"First, the verdict. {first_sentence(verdict) or 'The team came down clearly on this one.'} "
            + (f"Overall, it's a {grade}. " if grade else "")
            + (f"The headline numbers: {metric_blurb}." if metric_blurb else "")
        ),
    })

    # ----- ch2: scores (Responses) -----
    ch2_beats = [
        {"action": "clickTab", "value": "Responses"},
        {"action": "spotlight", "target": "text~:Score Distribution", "ms": 2600},
        {"action": "scrollTo", "target": "text~:Question-by-Question"},
        {"action": "spotlight", "target": "text~:Question-by-Question", "ms": 2200},
    ]
    rule_blurb = ""
    if rule_q:
        rule_blurb = f"The rule itself scored {rule_q.get('mean')} out of 5. "
    chapters.append({
        "kind": "chapter", "number": 2, "title": "How it scored", "section": "Responses",
        "dividerText": "Every question, scored and broken down.",
        "beats": ch2_beats,
        "narration": (
            f"How did it score? {rule_blurb}"
            + (f"{top_pick} came out as the clear favourite. " if top_pick else "")
            + "Each question opens up to show the full distribution and every individual answer."
        ),
    })

    # ----- ch3: themes -----
    top_themes = [t.get("name") for t in themes[:2] if t.get("name")]
    quote = notable[0] if notable else None
    ch3_beats = [
        {"action": "clickTab", "value": "Themes"},
        {"action": "spotlight", "target": "text~:Topic Stance", "ms": 2400},
        {"action": "scrollTo", "target": "text~:Key Themes"},
    ]
    if top_themes:
        ch3_beats.append({"action": "spotlight", "target": f"text~:{top_themes[0][:30]}", "ms": 2400})
    ch3_beats.append({"action": "scrollTo", "target": "text~:Notable Quotes"})
    ch3_beats.append({"action": "spotlight", "target": "text~:Notable Quotes", "ms": 2000})
    stance = so.get("spectrumLabel") or so.get("dominantStance") or ""
    theme_blurb = (" The strongest themes: " + "; ".join(top_themes) + ".") if top_themes else ""
    quote_blurb = ""
    if quote and quote.get("text"):
        who = quote.get("name") or quote.get("respondent") or ""
        quote_blurb = f' As {who} put it: "{first_sentence(quote.get("text"), 160)}"'
    chapters.append({
        "kind": "chapter", "number": 3, "title": "What the team said", "section": "Themes",
        "dividerText": "The team's opinions, in their own words.",
        "beats": ch3_beats,
        "narration": (
            f"Now, what the team actually said. {first_sentence(stance)}."
            + theme_blurb + quote_blurb
        ),
    })

    # ----- ch4: actions (Insights) -----
    ch4_beats = [
        {"action": "clickTab", "value": "Insights"},
        {"action": "spotlight", "target": "text~:Signals to Notice", "ms": 2400},
        {"action": "scrollTo", "target": "text~:Adoption Gaps"},
        {"action": "spotlight", "target": "text~:Adoption Gaps", "ms": 2000},
        {"action": "scrollTo", "target": "text~:Recommendations"},
        {"action": "spotlight", "target": "text~:Recommendations", "ms": 2400},
    ]
    top_signal = redflags[0].get("flag") if redflags else None
    top_gap = gaps[0].get("gap") if gaps else None
    imm = (recs.get("immediate") or [{}])[0].get("action") if recs.get("immediate") else None
    strat = (recs.get("strategic") or [{}])[0].get("action") if recs.get("strategic") else None
    action_bits = []
    if top_signal:
        action_bits.append(f"The signal to notice: {top_signal.lower()}")
    if top_gap:
        action_bits.append(f"the clearest gap is {top_gap.lower()}")
    chapters.append({
        "kind": "chapter", "number": 4, "title": "What SSW should do", "section": "Insights & Actions",
        "dividerText": "The signals worth noticing and the recommended next steps.",
        "beats": ch4_beats,
        "narration": (
            ("So what should we do? " + ". ".join(action_bits) + ". " if action_bits else "So what should we do? ")
            + (f"This week: {imm} " if imm else "")
            + (f"And longer term: {strat}." if strat else "")
        ),
    })

    # ----- outro -----
    chapters.append({
        "kind": "outro",
        "title": "That's this week",
        "subtitle": topic,
        "recap": chapter_titles,
        "narration": (
            "That's the digest. The full interactive dashboard has every question, "
            "every quote, and every person's answers. Thanks for watching."
        ),
    })

    plan = {
        "survey": topic,
        "date": date,
        "url": args.url,
        "accent": "#CC4141",
        "chapters": chapters,
    }
    json.dump(plan, open(args.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"[build-walkthrough-plan] wrote {args.out} ({len(chapters)} chapters)")


if __name__ == "__main__":
    main()
