#!/usr/bin/env python3
"""Self-check for the story consolidation: context.json merge, story beats and
debates, question tags (qnum) on every quote, the headline number check and
the one-file-per-run rule.
Run: python3 templates/test_story_consolidation.py
"""
import csv
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

spec = importlib.util.spec_from_file_location(
    "bc", os.path.join(os.path.dirname(__file__), "build-consolidated.py"))
bc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bc)

HEADERS = ["Id", "Name", "Email", "Rate the rule", "How often do you update it?",
           "What did you change?", "Any war stories?"]
ROWS = [
    ["1", "Alice Smith", "a@x.com", "5", "1. Daily",
     "I moved our test commands into CLAUDE.md so it stops guessing.",
     "The agent deleted a migration once and I never forgot it."],
    ["2", "Bob Jones", "b@x.com", "4", "1. Daily",
     "Nothing yet, I still correct it in chat every time.",
     "It kept using the wrong package manager for a week."],
    ["3", "Cara Lee", "c@x.com", "4", "2. Weekly",
     "Split one huge instruction file into three small skills.",
     "A nightly job editing config sounds risky to me."],
    ["4", "Dan Wu", "d@x.com", "5", "1. Daily",
     "Added a hook that blocks force pushes to main.",
     "Retros found three repeat issues in a single afternoon."],
    ["5", "Eve Park", "e@x.com", "3", "2. Weekly",
     "Removed stale rules that nobody followed anymore.",
     "I would let it propose changes but never apply them."],
]

QUANT = {
    "metadata": {"topic": "AI config"},
    "beats": [
        {"headline": "60% update their config every day", "qids": ["q2"],
         "quotes": [{"name": "Alice Smith",
                     "text": "I moved our test commands into CLAUDE.md so it stops guessing."}]},
        {"headline": "90% update it weekly", "qids": ["q2"], "quotes": []},
        {"headline": "A beat about nothing", "qids": ["q99"], "quotes": []},
        {"headline": "Spliced", "qids": ["q2"],
         "quotes": [{"name": "Alice Smith",
                     "text": "I moved our test commands into CLAUDE.md so it stops guessing. "
                             "The agent deleted a migration once and I never forgot it."}]},
    ],
}
QUAL = {
    "themes": [{
        "id": "t1", "name": "Fix it at the root", "appearsInQuestions": ["qt1"],
        "representativeQuote": {"name": "Dan Wu", "text": "Added a hook that blocks force pushes to main.",
                                "question": "What did you change?"},
        "allQuotes": [
            {"name": "Dan Wu", "text": "Added a hook that blocks force pushes to main.",
             "question": "What did you change?"},
            {"name": "Cara Lee", "text": "Split one huge instruction file into three small skills.",
             "question": "What did you change?"},
        ],
    }],
    "notableQuotes": [{"name": "Bob Jones", "text": "It kept using the wrong package manager for a week.",
                       "question": "Any war stories?"}],
    "standoutResponses": [{"name": "Eve Park", "response": "I would let it propose changes but never apply them.",
                           "question": "Any war stories?", "whyStandout": "Nuanced"}],
    "debates": [
        {"qids": ["qt2"], "question": "Should an agent edit its own config?",
         "sides": [
             {"label": "Let it propose", "quotes": [
                 {"name": "Eve Park", "text": "I would let it propose changes but never apply them."}]},
             {"label": "Too risky", "quotes": [
                 {"name": "Cara Lee", "text": "A nightly job editing config sounds risky to me."}]},
         ]},
        {"qids": ["qt2"], "question": "One-sided",
         "sides": [
             {"label": "Real", "quotes": [
                 {"name": "Dan Wu", "text": "Retros found three repeat issues in a single afternoon."}]},
             {"label": "Invented", "quotes": [
                 {"name": "Bob Jones", "text": "I think agents should run the whole company."}]},
         ]},
    ],
}
CONTEXT = {
    "idea": "Treat the config like code: fix the root cause, not the chat.",
    "rule": {"title": "Do you run retros on your AI agent?", "url": None,
             "summary": "Review your sessions and fix repeat mistakes at the root."},
    "video": None,
    "task": {"title": "Ship one fix", "summary": "Change one thing in your config."},
    "questions": {"q1": {"summary": "How good was the rule?", "missingOptions": []}},
}


def make_run(with_context=True, extra_csv=False):
    root = tempfile.mkdtemp()
    adir = os.path.join(root, "analysis")
    os.makedirs(adir)
    with open(os.path.join(root, "data.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADERS)
        w.writerows(ROWS)
    if extra_csv:
        with open(os.path.join(root, "other.csv"), "w") as f:
            f.write("Name,Q\nZed,hi\n")
    for name, obj in (("quantitative.json", QUANT), ("qualitative.json", QUAL)):
        with open(os.path.join(adir, name), "w") as f:
            json.dump(obj, f)
    if with_context:
        with open(os.path.join(adir, "context.json"), "w") as f:
            json.dump(CONTEXT, f)
    return adir


def run(adir):
    """Run build-consolidated main(); returns (exit code, consolidated or None)."""
    out = os.path.join(adir, "consolidated.json")
    argv = sys.argv
    sys.argv = ["build-consolidated.py", adir, "--no-photos", "--topic", "AI config",
                "--rule-url", "https://www.ssw.com.au/rules/run-retros-on-your-ai-agent"]
    code = 0
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            bc.main()
    except SystemExit as e:
        code = e.code or 0
    finally:
        sys.argv = argv
    if code or not os.path.exists(out):
        return code, None
    with open(out) as f:
        return code, json.load(f)


def all_quotes(c):
    for t in c["themes"]:
        yield from t["allQuotes"]
        yield t["representativeQuote"]
    yield from c["notableQuotes"]
    yield from c["standoutResponses"]
    for b in c["story"]["beats"]:
        yield from b["quotes"]
    for d in c["story"]["debates"]:
        for s in d["sides"]:
            yield from s["quotes"]


def test_context_merged_with_catalogue(c):
    q1 = c["context"]["questions"][0]
    assert q1["number"] == "Q1" and q1["qid"] == "q1", q1
    assert q1["summary"] == "How good was the rule?"
    assert c["context"]["rule"]["summary"].startswith("Review your sessions")
    # rule.url falls back to --rule-url
    assert c["context"]["rule"]["url"] == "https://www.ssw.com.au/rules/run-retros-on-your-ai-agent"
    assert c["context"]["video"] is None
    assert [q["number"] for q in c["context"]["questions"]] == ["Q1", "Q2", "Q3", "Q4"]
    assert c["questionBreakdown"][0]["number"] == "Q1"
    assert c["freeTextQuestions"][0]["number"] == "Q3"


def test_every_quote_has_qnum(c):
    quotes = list(all_quotes(c))
    assert len(quotes) >= 7, len(quotes)
    for q in quotes:
        assert re.fullmatch(r"Q\d+", q.get("qnum") or ""), q
    rep = c["themes"][0]["representativeQuote"]
    assert rep["qnum"] == "Q3", rep
    assert c["standoutResponses"][0]["qnum"] == "Q4"
    beat = c["story"]["beats"][0]
    assert beat["quotes"][0]["qnum"] == "Q3" and beat["quotes"][0]["respondent"] == "Alice Smith"


def unlocatable_quote_is_dropped_and_reported(c):
    spliced = [b for b in c["story"]["beats"] if b["headline"] == "Spliced"]
    assert spliced and spliced[0]["quotes"] == [], spliced
    assert c["consolidationNotes"]["untaggedDropped"] >= 1


def test_beat_with_unknown_qids_dropped(c):
    assert "A beat about nothing" not in [b["headline"] for b in c["story"]["beats"]]


def test_number_check_flags_wrong_percent(c):
    nc = c["consolidationNotes"]["numberCheck"]
    assert nc["checked"] >= 2, nc
    assert nc["unmatched"] == [{"headline": "90% update it weekly", "number": "90%"}], nc


def test_one_sided_debate_dropped(c):
    debates = c["story"]["debates"]
    assert [d["question"] for d in debates] == ["Should an agent edit its own config?"], debates
    assert [s["label"] for s in debates[0]["sides"]] == ["Let it propose", "Too risky"]


def test_legacy_fields_kept(c):
    for k in ("metadata", "executiveSummary", "overallGrade", "keyMetrics", "notableQuotes",
              "people", "photos"):
        assert k in c, k


def test_two_data_files_is_an_error():
    code, c = run(make_run(extra_csv=True))
    assert code == 1 and c is None, code


def test_missing_context_json_is_fine():
    code, c = run(make_run(with_context=False))
    assert code == 0, code
    assert c["context"]["idea"] is None and c["context"]["rule"]["url"].endswith("ai-agent")
    assert len(c["context"]["questions"]) == 4
    assert all(q["summary"] == "" for q in c["context"]["questions"])


def main():
    code, c = run(make_run())
    assert code == 0, code
    for t in (test_context_merged_with_catalogue, test_every_quote_has_qnum,
              unlocatable_quote_is_dropped_and_reported, test_beat_with_unknown_qids_dropped,
              test_number_check_flags_wrong_percent, test_one_sided_debate_dropped,
              test_legacy_fields_kept):
        t(c)
    test_two_data_files_is_an_error()
    test_missing_context_json_is_fine()
    print("test_story_consolidation: OK")


if __name__ == "__main__":
    sys.exit(main())
