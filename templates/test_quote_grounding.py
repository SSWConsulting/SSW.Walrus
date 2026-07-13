#!/usr/bin/env python3
"""Self-check for the QuoteGrounder anti-hallucination gate.
Run: python3 templates/test_quote_grounding.py
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


def main():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", newline="", delete=False) as f:
        w = csv.writer(f)
        w.writerow(["Name", "Q1", "Q2"])
        w.writerow(["Alice Smith", "The CLI is great for whole-codebase refactors.",
                    "I used it every day this sprint. My favourite feature is subagents."])
        w.writerow(["Bob Jones", "Not convinced yet — the web UI is better for research.", ""])
        path = f.name

    g = bc.QuoteGrounder([path])

    # verbatim passes untouched (case/punctuation-insensitive)
    assert g.ground("Alice Smith", "The CLI is great for whole-codebase refactors.") == \
        "The CLI is great for whole-codebase refactors."
    # sentence splice of things Alice really wrote passes
    assert g.ground("Alice Smith",
                    "I used it every day this sprint. The CLI is great for whole-codebase refactors.") is not None
    # near-match (agent 'fixed' wording) is repaired to the real cell text
    assert g.ground("Bob Jones", "Not convinced yet — the web UI is better for researching.") == \
        "Not convinced yet — the web UI is better for research."
    # fabrication is dropped
    assert g.ground("Alice Smith", "Claude Code changed my life, 10/10, everyone should switch!") is None
    # quote misattributed to the wrong person is dropped
    assert g.ground("Alice Smith", "Not convinced yet — the web UI is better for research.") is None

    assert g.dropped == 2 and g.repaired == 1, (g.dropped, g.repaired)

    # extract_survey: bulk data comes from the file, classified deterministically
    rows = [
        {"ID": str(i), "Name": f"Person {i}",
         "Rate the video": str(3 + i % 3),
         "Favourite tool": f"{1 + i % 2}. {'Claude Code' if i % 2 else 'Copilot CLI'}",
         "Tools tried": "1. Copilot CLI;2. Claude Code;",
         "Your thoughts": f"Free text opinion number {i} with unique content",
         "🍔 Free Lunch - order form": "1. Done"}
        for i in range(10)
    ]
    ex = bc.extract_survey(rows)
    kinds = {q["text"]: q["kind"] for q in ex["questions"]}
    assert kinds["Rate the video"] == "rating"
    assert kinds["Favourite tool"] == "single-select"
    assert kinds["Tools tried"] == "multi-select"
    assert [q["text"] for q in ex["freeText"]] == ["Your thoughts"]
    assert ex["excluded"][0]["text"].startswith("🍔")
    rating = next(q for q in ex["questions"] if q["kind"] == "rating")
    vals = [3 + i % 3 for i in range(10)]
    assert rating["mean"] == round(sum(vals) / len(vals), 1)
    assert len(rating["individualResponses"]) == 10
    fav = next(q for q in ex["questions"] if q["text"] == "Favourite tool")
    assert set(fav["distribution"]) == {"Claude Code", "Copilot CLI"}  # "N. " prefix stripped

    os.unlink(path)
    print("test_quote_grounding: OK")


if __name__ == "__main__":
    main()
