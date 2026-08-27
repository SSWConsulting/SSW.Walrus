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
    return bc.load_rows(path)      # read only once the writer has flushed


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

    print("test_blockers: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
