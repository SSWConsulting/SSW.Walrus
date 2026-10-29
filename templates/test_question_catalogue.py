#!/usr/bin/env python3
"""Self-check for the code-built question catalogue (form order, Q numbers,
option order, N/A-free percentages).
Run: python3 templates/test_question_catalogue.py
"""
import csv
import importlib.util
import os
import sys
import tempfile

spec = importlib.util.spec_from_file_location(
    "bc", os.path.join(os.path.dirname(__file__), "build-consolidated.py"))
bc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bc)

NA = "8. N/A - I'm not a dev"
LONG = ("Exercise: Ship one fix to your AI config 1. Start a timer 2. Run /insights or a retro "
        "skill over your last week of sessions 3. Pick the one correction you typed most often "
        "4. Fix it at the root in AGENTS.md, a skill or a hook 5. Paste the diff below "
        "https://github.com/example/skills/tree/mai")
# The 23/10 export cut headers at 200 chars ("…/skills/tree/mai")
CUT200 = ("Read the rule and give it a rating Do you run retros on your AI agent? "
          "https://www.ssw.com.au/rules/run-retros-on-your-ai-agent Tip: Read the rule and "
          "give it a rating. You can make changes yourself using th")
# long but complete (ends with a full stop) — not truncated
FULL190 = ("Would you let an agent propose improvements to your AI config while you sleep? "
           "A nightly job reads your agent sessions, finds repeat corrections, and proposes "
           "fixes you approve each morning.")
HEADERS = ["Id", "Name", "Email", "Rate the rule", "Your current project - name",
           "How often?", "Which cadence at work?", "Dev-only question", "Free text",
           LONG, CUT200, FULL190, "Are you currently blocked?"]
ROWS = [
    ["1", "Alice Smith", "a@x.com", "5", "Northwind", "2. Weekly", "1. Daily", "3. N/A - I'm not a dev",
     "I fix the config whenever it repeats a mistake.", "Added a hook that blocks force pushes.", "Rule answer number 1 here.", "Nightly answer number 1 here.", "No"],
    ["2", "Bob Jones", "b@x.com", "4", "Contoso", "1. Daily", "1. Daily", "3. N/A - I'm not a dev",
     "Mostly I just correct it in chat, honestly.", "Wrote a skill for our release notes.", "Rule answer number 2 here.", "Nightly answer number 2 here.", "No"],
    ["3", "Cara Lee", "c@x.com", "3", "Fabrikam", NA, "1. Daily", "3. N/A - I'm not a dev",
     "I don't write code so this was new to me.", "Not applicable for my role this week.", "Rule answer number 3 here.", "Nightly answer number 3 here.", "No"],
    ["4", "Dan Wu", "d@x.com", "5", "Tailspin", "as needed", "2. Weekly", "3. N/A - I'm not a dev",
     "Retros on agent sessions found three repeat issues.", "Moved test commands into CLAUDE.md.", "Rule answer number 4 here.", "Nightly answer number 4 here.", "No"],
    ["5", "Eve Park", "e@x.com", "4", "Litware", "1. Daily", NA, "3. N/A - I'm not a dev",
     "Skills beat long instruction files for us.", "Split our AGENTS.md into two skills.", "Rule answer number 5 here.", "Nightly answer number 5 here.", "No"],
    ["6", "Finn Ode", "f@x.com", "4", "Adatum", "2. Weekly", NA, "3. N/A - I'm not a dev",
     "Nightly jobs editing config sounds risky to me.", "Removed stale rules from the config.", "Rule answer number 6 here.", "Nightly answer number 6 here.", "Yes"],
    ["7", "Gus Hal", "g@x.com", "5", "Proseware", "1. Daily", "", "3. N/A - I'm not a dev",
     "Weekly tinkering keeps the agent sharp.", "Added a lint step to the stop hook.", "Rule answer number 7 here.", "Nightly answer number 7 here.", "No"],
]


def extract():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", newline="", delete=False) as f:
        w = csv.writer(f)
        w.writerow(HEADERS)
        w.writerows(ROWS)
        path = f.name
    try:
        return bc.extract_survey(bc.load_rows(path))
    finally:
        os.unlink(path)


def by_text(ex, text):
    return next(q for q in ex["questions"] + ex["freeText"] if q["text"] == text)


def test_numbers_follow_column_order(ex):
    cat = bc.build_question_catalogue(ex)
    got = [(q["number"], q["text"][:20], q["type"]) for q in cat["questions"]]
    assert got == [
        ("Q1", "Rate the rule", "rating"),
        ("Q2", "How often?", "single-select"),
        ("Q3", "Which cadence at wor", "single-select"),
        ("Q4", "Dev-only question", "single-select"),
        ("Q5", "Free text", "free-text"),
        ("Q6", LONG[:20], "free-text"),
        ("Q7", CUT200[:20], "free-text"),
        ("Q8", FULL190[:20], "free-text"),
    ], got
    kinds = {e["text"]: e["kind"] for e in cat["excluded"]}
    assert kinds == {"Your current project - name": "context",
                     "Are you currently blocked?": "admin"}, kinds
    # existing ids are unchanged by the context demotion (agents reference them)
    assert by_text(ex, "Rate the rule")["id"] == "q1"
    assert by_text(ex, "Free text")["id"] == "qt2", by_text(ex, "Free text")["id"]


def test_option_order_uses_prefix_then_write_ins(ex):
    q = by_text(ex, "How often?")
    assert q["optionOrder"] == ["Daily", "Weekly", "N/A - I'm not a dev", "as needed"], q["optionOrder"]
    assert q["optionNumbers"] == {"Daily": 1, "Weekly": 2, "N/A - I'm not a dev": 8, "as needed": None}
    assert q["naOptions"] == ["N/A - I'm not a dev"]
    # write-ins (no N. prefix) are one-off "Other" answers, not form options
    assert q["writeIns"] == ["as needed"]
    assert q["otherCount"] == 1 and q["otherPercent"] == 17, (q["otherCount"], q["otherPercent"])
    cat = bc.build_question_catalogue(ex)
    assert cat["questions"][1]["options"] == ["Daily", "Weekly", "N/A - I'm not a dev"]
    assert cat["questions"][1]["hasOther"] is True
    assert cat["questions"][2]["hasOther"] is False


def test_percentages_exclude_na(ex):
    q = by_text(ex, "Which cadence at work?")
    assert q["base"] == 4, q["base"]
    assert q["baseLabel"] == "devs"
    assert q["percentages"] == {"Daily": 75, "Weekly": 25}, q["percentages"]


def all_na_question_has_zero_base_and_no_percentages(ex):
    q = by_text(ex, "Dev-only question")
    assert q["base"] == 0
    assert q["percentages"] == {}


def test_truncated_flag(ex):
    assert by_text(ex, LONG)["truncated"] is True
    assert by_text(ex, "Free text")["truncated"] is False
    assert by_text(ex, "Rate the rule")["truncated"] is False
    assert by_text(ex, CUT200)["truncated"] is True
    assert by_text(ex, FULL190)["truncated"] is False


def main():
    ex = extract()
    for t in (test_numbers_follow_column_order, test_option_order_uses_prefix_then_write_ins,
              test_percentages_exclude_na, all_na_question_has_zero_base_and_no_percentages,
              test_truncated_flag):
        t(ex)
    print("test_question_catalogue: OK")


if __name__ == "__main__":
    sys.exit(main())
