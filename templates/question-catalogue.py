#!/usr/bin/env python3
"""
question-catalogue.py — print a survey's question catalogue as JSON.

Every topic question in form order with its Q number, type, (possibly
truncated) header text and observed options, plus the admin/context columns
that are left out. The process-survey skill runs this in Step 1, writes
analysis/context.json from it, and hands it to every analysis agent.

Usage: python3 question-catalogue.py <data.csv|data.xlsx>
"""
import importlib.util
import json
import os
import sys

spec = importlib.util.spec_from_file_location(
    "bc", os.path.join(os.path.dirname(os.path.abspath(__file__)), "build-consolidated.py"))
bc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bc)


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: question-catalogue.py <data.csv|data.xlsx>\n")
        return 1
    extracted = bc.extract_survey(bc.load_rows(sys.argv[1]))
    if not extracted:
        sys.stderr.write("[question-catalogue] error: no rows in survey file\n")
        return 1
    json.dump(bc.build_question_catalogue(extracted), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
