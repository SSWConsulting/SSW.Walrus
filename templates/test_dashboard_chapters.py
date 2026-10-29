#!/usr/bin/env python3
"""Self-check for the chapter dashboard renderer (build-dashboard.py): chapter
order, Next buttons, skipped chapters, the priming chapter and question tags.
Run: python3 templates/test_dashboard_chapters.py
"""
import copy
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bd", os.path.join(HERE, "build-dashboard.py"))
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)

CHAPTER_NAMES = ["The topic", "Where the team is at", "In their own words", "Hot takes", "What's next"]


def quote(name, text, qnum, question="Q text"):
    return {"respondent": name, "name": name, "text": text, "question": question, "qnum": qnum}


FIXTURE = {
    "metadata": {"surveyName": "AI config", "topic": "Treat your AI config as a living product",
                 "responseCount": 51, "completionRate": 100, "dateRange": "23/10/2026"},
    "executiveSummary": {"bullets": ["A bullet"], "overallVerdict": "Strong uptake, thin follow-through."},
    "overallGrade": "B",
    "context": {
        "idea": "Fix the config, not the chat.",
        "rule": {"title": "Do you run retros on your AI agent?", "url": "https://www.ssw.com.au/rules/x",
                 "summary": "Review sessions, fix repeats at the root."},
        "video": {"title": "Matt Pocock's New Skill", "url": "https://youtu.be/x", "length": "9 min",
                  "optional": True},
        "task": {"title": "Ship one fix", "summary": "Change one thing in your config."},
        "questions": [
            {"qid": "q1", "number": "Q1", "type": "rating", "text": "Read the rule and give it a rating",
             "truncated": True, "summary": "How useful was the rule?", "options": [], "missingOptions": []},
            {"qid": "q2", "number": "Q2", "type": "single-select", "text": "How often do you update it?",
             "truncated": False, "summary": "", "options": ["Every day", "Every week", "N/A - I'm not a dev"],
             "missingOptions": ["Never"]},
            {"qid": "q3", "number": "Q3", "type": "rating", "text": "Rate the value of this week's task",
             "truncated": False, "summary": "", "options": [], "missingOptions": []},
            {"qid": "q4", "number": "Q4", "type": "single-select", "text": "Same mistake twice?",
             "truncated": False, "summary": "", "options": ["Fix the root", "Correct in chat"],
             "missingOptions": []},
            {"qid": "qt2", "number": "Q5", "type": "free-text", "text": "What did you change?",
             "truncated": False, "summary": "", "options": [], "missingOptions": []},
        ],
        "excluded": [{"text": "Your current project - name", "kind": "context"},
                     {"text": "Are you currently blocked by me or anyone else?", "kind": "admin"}],
    },
    "story": {
        "beats": [
            {"headline": "77% of devs fix the config, not the chat", "qids": ["q4"],
             "quotes": [quote("Alice Smith", "I fixed it at the root.", "Q4")]},
            {"headline": "Most update weekly", "qids": ["q2"], "quotes": []},
        ],
        "debates": [{"qids": ["qt2"], "question": "Should an agent edit its own config?",
                     "sides": [{"label": "Let it propose", "quotes": [quote("Eve Park", "Propose only.", "Q5")]},
                               {"label": "Too risky", "quotes": [quote("Cara Lee", "Sounds risky.", "Q5")]}]}],
    },
    "questionBreakdown": [
        {"id": "q1", "number": "Q1", "kind": "rating", "text": "Read the rule and give it a rating",
         "mean": 4.2, "scaleMax": 5, "distribution": {"3": 5, "4": 20, "5": 26}, "responseCount": 51,
         "individualResponses": [{"respondent": "Alice Smith", "value": 5.0}], "insight": "Rule landed well."},
        {"id": "q2", "number": "Q2", "kind": "single-select", "text": "How often do you update it?",
         "distribution": {"Every day": 10, "Every week": 20, "N/A - I'm not a dev": 10},
         "optionOrder": ["Every day", "Every week", "N/A - I'm not a dev"],
         "naOptions": ["N/A - I'm not a dev"], "base": 30, "baseLabel": "devs",
         "percentages": {"Every day": 33, "Every week": 67}, "responseCount": 40,
         "individualResponses": [{"respondent": "Bob Jones", "value": "Every week"}],
         "insight": "Weekly tinkering is the norm."},
        {"id": "q3", "number": "Q3", "kind": "rating", "text": "Rate the value of this week's task",
         "mean": 3.9, "scaleMax": 5, "distribution": {"3": 15, "4": 25, "5": 11}, "responseCount": 51,
         "individualResponses": [], "insight": "Task value was middling."},
        {"id": "q4", "number": "Q4", "kind": "single-select", "text": "Same mistake twice?",
         "distribution": {"Fix the root": 31, "Correct in chat": 10},
         "optionOrder": ["Fix the root", "Correct in chat"], "naOptions": [], "base": 41,
         "baseLabel": "devs", "percentages": {"Fix the root": 77, "Correct in chat": 23},
         "responseCount": 41, "individualResponses": [], "insight": "Root-cause fixing dominates."},
    ],
    "freeTextQuestions": [
        {"id": "qt2", "number": "Q5", "text": "What did you change?", "responseCount": 2,
         "curated": [{"respondent": "Dan Wu", "text": "Added a hook."}],
         "responses": [{"respondent": "Dan Wu", "text": "Added a hook."},
                       {"respondent": "Eve Park", "text": "Removed stale rules."}]},
    ],
    "themes": [{"id": "t1", "name": "Fix it at the root", "frequency": 5, "frequencyPercent": 10,
                "sentiment": "positive",
                "representativeQuote": quote("Dan Wu", "Added a hook.", "Q5"),
                "allQuotes": [quote(n, f"Quote {i} from {n}.", "Q5") for i, n in
                              enumerate(["Dan Wu", "Eve Park", "Cara Lee", "Bob Jones", "Gus Hal"])]}],
    "notableQuotes": [],
    "standoutResponses": [{"respondent": "Eve Park", "name": "Eve Park", "question": "What did you change?",
                           "response": "Removed stale rules.", "text": "Removed stale rules.",
                           "whyStandout": "Contrarian", "qnum": "Q5"}],
    "sentimentOverview": {"spectrumLabel": "Strongly adopted", "dominantStance": "pragmatism",
                          "emotionalBreakdown": {"enthusiasm": 40, "pragmatism": 50}},
    "people": {"respondents": [{"name": "Alice Smith", "averageScore": 5.0, "responseCount": 2,
                                "numericResponses": [], "textResponses": [], "flags": [], "photoUrl": None}]},
    "photos": {},
    "redFlags": [{"flag": "Skeptic worth hearing", "severity": "low", "evidence": "Some doubt."}],
    "adoptionGaps": [{"gap": "Few retros", "evidence": "Only 10%", "opportunity": "Run a session"}],
    "recommendations": {"immediate": [{"action": "Share the top fixes", "owner": "Host"}],
                        "shortTerm": [], "strategic": []},
    "hardTruths": ["People say root cause, but few run retros."],
    "focusSummary": None,
}


def render(c):
    d = tempfile.mkdtemp()
    cp, out = os.path.join(d, "c.json"), os.path.join(d, "index.html")
    with open(cp, "w") as f:
        json.dump(c, f)
    argv = sys.argv
    sys.argv = ["build-dashboard.py", cp, os.path.join(HERE, "survey-dashboard.html"), out]
    try:
        with redirect_stdout(io.StringIO()):
            bd.main()
    finally:
        sys.argv = argv
    with open(out) as f:
        return f.read()


def chapter(html, cid):
    """The HTML of one chapter section (data-chapter="cid") up to the next."""
    m = re.search(rf'data-chapter="{cid}"(.*?)(?=data-chapter="|$)', html, re.S)
    return m.group(1) if m else None


def nav(html):
    m = re.search(r'<aside class="ds-sidebar.*?</aside>', html, re.S)
    return m.group(0)


def without(**drop):
    c = copy.deepcopy(FIXTURE)
    for k, v in drop.items():
        if v is None:
            c.pop(k, None)
        else:
            c[k] = v
    return c


def test_nav_order_and_people_last(html):
    n = nav(html)
    pos = [n.find(f">{bd.esc(name)}<") for name in CHAPTER_NAMES + ["People"]]
    assert all(p >= 0 for p in pos), pos
    assert pos == sorted(pos), pos


def test_next_buttons_chain(html):
    assert "Next: Where the team is at →" in chapter(html, "topic")
    assert "Next: In their own words →" in chapter(html, "team")
    assert "Next: Hot takes →" in chapter(html, "words")
    assert "Next: What&#x27;s next →" in chapter(html, "takes")
    assert "← Back to the start" in chapter(html, "next")


def test_takes_skipped_when_empty():
    c = without(standoutResponses=[], story={"beats": FIXTURE["story"]["beats"], "debates": []})
    html = render(c)
    assert ">Hot takes<" not in html
    assert chapter(html, "takes") is None
    assert "Next: What&#x27;s next →" in chapter(html, "words")


def test_topic_lists_questions_with_numbers_and_options(html):
    t = chapter(html, "topic")
    for n in ("Q1", "Q2", "Q3", "Q4", "Q5"):
        assert f">{n}<" in t, n
    assert "How useful was the rule?" in t           # summary shown for Q1
    assert "summarised" in t                          # Q1 was cut off in the export
    assert "Every week" in t and "Never" in t and "(deduced)" in t
    assert "Do you run retros on your AI agent?" in t and "9 min" in t and "Ship one fix" in t
    assert "Left out:" in t and "Your current project" in t
    assert "Friday 23/10/2026" in t and "51 people answered" in t


def missing_context_renders_topic_and_questions():
    html = render(without(context=None, story=None))
    t = chapter(html, "topic")
    assert "Treat your AI config as a living product" in t
    for n in ("Q1", "Q2", "Q3", "Q4", "Q5"):
        assert f">{n}<" in t, n
    assert "The rule they read" not in t


def test_no_responses_or_overview_tab(html):
    assert "activeTab === 'responses'" not in html
    assert "activeTab === 'overview'" not in html


def main():
    html = render(FIXTURE)
    test_nav_order_and_people_last(html)
    test_next_buttons_chain(html)
    test_topic_lists_questions_with_numbers_and_options(html)
    test_no_responses_or_overview_tab(html)
    test_takes_skipped_when_empty()
    missing_context_renders_topic_and_questions()
    print("test_dashboard_chapters: OK")


if __name__ == "__main__":
    sys.exit(main())
