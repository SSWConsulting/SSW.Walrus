#!/usr/bin/env python3
"""Self-check for the standing blocked question -> Blockers tab extraction.
Run: python3 templates/test_blockers.py

The cast is fictional on purpose. This repo is public, so a fixture must never
carry real names and real internal friction — even invented detail text reads as
a genuine record once it sits next to a real person's name.
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

STANDING = ('Are you currently blocked by me or anyone else? Tip: "blocked" means you '
            'have tried to reach out - say 2 times over 2 days')
FOLLOWUP = "1. Who + what was blocking you? 2. Include the related email subject"
# A topic question that also says "block" — the trap that breaks position-based reads.
TOPIC = "How often are you blocked waiting on a UI/UX decision?"
OWNER = "Sam Carter"      # whoever the standing question is asked in the voice of


def rows_from(headers, records):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", newline="", delete=False) as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(records)
        path = f.name
    try:
        return bc.load_rows(path)  # read only once the writer has flushed
    finally:
        os.unlink(path)


def main():
    rows = rows_from(
        ["Name", "Email", TOPIC, STANDING, FOLLOWUP],
        [
            # a topic question sharing the word "block" must not win
            ["Alice Smith", "alice@example.com", "3. Weekly", "1. Yes - for more than a day",
             "The newsletter draft, still unreviewed"],
            ["Bob Jones", "bob@example.com", "2. Monthly", "2. Yes - for a few hours",
             "Sign-off on the pricing page"],
            ["Cara Diaz", "cara@example.com", "1. Rarely", "3. Yes - for about an hour", "N/A"],
            ["Dev Patel", "dev@example.com", "1. Rarely",
             "4. No - someone else was blocking me", "Waiting on Erin Fox for a review"],
            ["Erin Fox", "erin@example.com", "1. Rarely", "5. No - had a good week", ""],
            ["Femi Okafor", "femi@example.com", "2. Monthly", "6. N/A - I'm not a dev", ""],
            # typed into the "Other" box: opens with "No", says the opposite
            ["Gus Reyes", "gus@example.com", "1. Rarely",
             "No - But I was during the week", "no reply on chat all week"],
        ])

    b = bc.extract_blockers(rows, OWNER)
    assert b, "the standing question was not detected"
    assert b["question"].startswith("Are you currently blocked"), b["question"]
    assert b["detailQuestion"].startswith("1. Who + what"), b["detailQuestion"]

    # counts
    assert b["responseCount"] == 7, b["responseCount"]
    assert b["blockedCount"] == 4, b["blockedCount"]          # 3 yes + 1 someone-else
    assert b["byOwner"] == 3, b["byOwner"]
    assert b["bySomeoneElse"] == 1, b["bySomeoneElse"]
    assert b["notBlocked"] == 1, b["notBlocked"]
    assert b["notApplicable"] == 1, b["notApplicable"]
    assert b["severityCounts"] == {"high": 1, "moderate": 1, "low": 1}, b["severityCounts"]

    # the "Other" answer is never auto-classified — a human reads it
    assert len(b["needsReview"]) == 1, b["needsReview"]
    assert b["needsReview"][0]["respondent"] == "Gus Reyes"
    assert all(p["respondent"] != "Gus Reyes" for p in b["people"])

    # ordered worst-first
    assert [p["respondent"] for p in b["people"][:3]] == \
        ["Alice Smith", "Bob Jones", "Cara Diaz"], b["people"]

    # attribution: "Yes" means the person the question is asked in the voice of
    assert b["people"][0]["blockedBy"] == OWNER
    assert b["people"][0]["detail"] == "The newsletter draft, still unreviewed"
    # "N/A" in the follow-up box means no detail, not a detail reading "N/A"
    assert b["people"][2]["detail"] == "", b["people"][2]
    # someone-else: the colleague is named from the survey's own roster
    other = [p for p in b["people"] if p["blockedBy"] != OWNER][0]
    assert other["respondent"] == "Dev Patel"
    assert other["blockedBy"] == "Erin Fox", other["blockedBy"]
    # ...and that option states no duration, so it gets no invented severity
    assert other["severity"] is None and other["severityLabel"] == "", other

    # no name given -> neutral label rather than a name
    assert bc.extract_blockers(rows)["people"][0]["blockedBy"] == "the person who asked"

    # the blocked columns are held out of the topic questions
    extracted = bc.extract_survey(rows, b["sourceColumns"])
    texts = [q["text"] for q in extracted["questions"]] + \
            [q["text"] for q in extracted["freeText"]]
    assert not any(t.startswith("Are you currently blocked") for t in texts), texts
    assert not any(t.startswith("1. Who + what") for t in texts), texts
    assert any(t == TOPIC for t in texts), "the topic question must survive"

    # a survey with no standing question gets no tab at all
    plain = rows_from(["Name", "Rate the video"],
                      [["Alice Smith", "4"], ["Bob Jones", "5"]])
    assert bc.extract_blockers(plain) is None

    # ...including one that merely mentions blocking in a topic question
    topic_only = rows_from(["Name", TOPIC],
                           [["Alice Smith", "3. Weekly"], ["Bob Jones", "1. Rarely"]])
    assert bc.extract_blockers(topic_only) is None, "a topic question must not pose as the standing one"

    regressions()
    print("test_blockers: all assertions passed")
    return 0


def regressions():
    """Cases found in review. Each one shipped a wrong answer to a reader."""

    # A free-text topic question that also says "block", sitting BEFORE the
    # standing question, used to win the detail slot — so the Blockers tab
    # printed an unrelated answer as what was blocking that person.
    TOPIC_FT = "What is blocking you from using stacked PRs more often?"
    rows = rows_from(
        ["Name", TOPIC_FT, STANDING, FOLLOWUP],
        [["Alice Smith", "no time, too busy with client work",
          "1. Yes - for more than a day", "Sam, the pricing sign-off"],
         ["Bob Jones", "our repo tooling is not there", "5. No - had a good week", ""],
         ["Cara Diaz", "reviewers are slow", "4. No - someone else was blocking me",
          "waiting on Erin"],
         ["Dev Patel", "habit, mostly", "5. No - had a good week", ""],
         ["Erin Fox", "nothing really", "1. Yes - for more than a day",
          "the staging access request"]])
    b = bc.extract_blockers(rows, OWNER)
    assert b["detailQuestion"].startswith("1. Who + what"), b["detailQuestion"]
    assert b["people"][0]["detail"] == "Sam, the pricing sign-off", b["people"][0]
    extracted = bc.extract_survey(rows, b["sourceColumns"])
    free = [q["text"] for q in extracted["freeText"]]
    assert TOPIC_FT in free, free                       # the topic question is still analysed
    assert not any(t.startswith("1. Who + what") for t in free), free

    # Respondents echo the follow-up's own numbering ("1. Who + what… 2. …"), so
    # a numbered-prefix test rejected the very column it was meant to find and
    # every card rendered "No detail given".
    rows = rows_from(
        ["Name", STANDING, FOLLOWUP],
        [["Alice Smith", "1. Yes - for more than a day", "1. Sam 2. Re: pricing sign-off"],
         ["Bob Jones", "1. Yes - for more than a day", "1. Sam 2. Re: newsletter"],
         ["Cara Diaz", "2. Yes - for a few hours", "1. Sam 2. staging access"],
         ["Dev Patel", "5. No - had a good week", ""]])
    b = bc.extract_blockers(rows, OWNER)
    assert b["detailQuestion"], "the numbered follow-up must still be found"
    assert all(p["detail"] for p in b["people"]), b["people"]

    # "N/A" is filler every free-text column collects. Counting it as standing
    # vocabulary grew a Blockers tab on a survey that has no such question.
    rows = rows_from(
        ["Name", "What is blocking your team from adopting Bicep?"],
        [["Alice Smith", "N/A"], ["Bob Jones", "N/A"],
         ["Cara Diaz", "no time"], ["Dev Patel", "N/A"]])
    assert bc.extract_blockers(rows) is None

    # A standing question worded so it is not detected must still be demoted,
    # not shown as a topic question.
    rows = rows_from(
        ["Name", "Are you currently blocked by me?", "Rate the video"],
        [["Alice Smith", "Sort of, yes", "4"], ["Bob Jones", "not really", "5"],
         ["Cara Diaz", "maybe", "3"]])
    extracted = bc.extract_survey(rows, ())
    assert not any("blocked by me" in q["text"]
                   for q in extracted["questions"] + extracted["freeText"])

    # Multi-file input concatenates rows whose headers differ, and the question is
    # re-worded between weeks. Reading headers from rows[0] dropped the rest.
    a = rows_from(["Name", STANDING, FOLLOWUP],
                  [["Alice Smith", "1. Yes - for more than a day", "the pricing sign-off"],
                   ["Bob Jones", "5. No - had a good week", ""]])
    other = ("I am working hard to block people less. Are you currently blocked by me? "
             "Tip: yes - for")
    c = rows_from(["Name", other, "If I blocked you, what was blocking you?"],
                  [["Cara Diaz", "1. Yes - for a few hours", "the staging access"],
                   ["Dev Patel", "1. Yes - for more than a day", "design review"]])
    b = bc.extract_blockers(a + c, OWNER)
    assert b["responseCount"] == 4, b["responseCount"]
    assert b["blockedCount"] == 3, b["blockedCount"]


if __name__ == "__main__":
    sys.exit(main())
