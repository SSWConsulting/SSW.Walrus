#!/usr/bin/env python3
"""
build-consolidated.py — deterministic consolidator for Chewing the Fat surveys.

Assembles consolidated.json — the single input the dashboard renderer, result
email, and recap video bind to — from two sources:

1. THE RAW SURVEY FILE (CSV/XLSX next to the analysis dir) — the source of
   truth for ALL bulk data: individual responses, tallies, means, distributions,
   people profiles, response counts. Extracted in code (`extract_survey`);
   no LLM is in this path.
2. The four analysis-agent outputs (quantitative / qualitative / sentiment /
   red-flags JSON) — synthesis only: themes, quotes, commentary, signals.
   Every quote they surface is verified against the raw file (`QuoteGrounder`).

WHY: LLM agents asked to re-emit bulk survey data fabricate it — a deployed run
was found with 95% of attributed quotes invented (real names, fake words).
Bulk data must come from the file; the LLM only analyses, never transcribes.

Usage:
  python3 build-consolidated.py <analysis-dir> \
      [--survey-name NAME] [--topic TOPIC] [--date DD/MM/YYYY] \
      [--rule-url URL] [--focus TEXT] [--data survey.csv|.xlsx] [--out PATH]

Reads  <analysis-dir>/{quantitative,qualitative,sentiment,red-flags}.json
       + the raw survey file (--data, or *.csv/*.xlsx next to <analysis-dir>)
Writes <analysis-dir>/consolidated.json (or --out).
"""

import argparse
import csv
import difflib
import glob
import json
import os
import re
import sys
import unicodedata
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ssw_people  # noqa: E402  (local module, same dir as this script)


# ----------------------------------------------------------------------------
# small helpers — defensive access (agents are LLMs; shapes drift)
# ----------------------------------------------------------------------------

def load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(f"[build-consolidated] warning: could not read {path}: {exc}\n")
        return {}


def first(d, *keys, default=None):
    """Return the first present, non-None key from a dict."""
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def name_of(obj):
    """Pull a respondent name out of a quote/response object regardless of key."""
    if not isinstance(obj, dict):
        return ""
    return str(first(obj, "respondent", "name", "author", default="") or "").strip()


STANCE_KEYS = ["enthusiasm", "pragmatism", "curiosity", "skepticism", "frustration", "indifference"]


def _num(v):
    """Coerce 38 / "38" / "38%" / 0.38 -> float; None on failure."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        if m:
            return float(m.group())
    return None


def extract_stance_breakdown(sentiment):
    """Find the six-stance breakdown wherever the sentiment agent put it.

    The agent spec is topicStance.spectrum.breakdown, but runs vary (nested under
    stance, top-level, alternate key). Search known spots, normalise keys to the
    six canonical stances, and return {} if nothing usable is found so the radar
    section can hide itself rather than draw an empty hexagon.
    """
    stance = sentiment.get("topicStance") or {}
    spectrum = stance.get("spectrum") or {}
    candidates = [
        spectrum.get("breakdown"),
        stance.get("breakdown"),
        stance.get("stanceProfile"),
        sentiment.get("breakdown"),
        sentiment.get("stanceProfile"),
        sentiment.get("emotionalBreakdown"),
    ]
    for cand in candidates:
        if not isinstance(cand, dict) or not cand:
            continue
        norm = {str(k).strip().lower(): v for k, v in cand.items()}
        got = {k: (_num(norm.get(k)) or 0) for k in STANCE_KEYS}
        if any(v for v in got.values()):
            return got
    return {}


def round1(x):
    try:
        return round(float(x) + 1e-9, 1)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------
# source-of-truth extraction — bulk data comes from the survey file, NOT the LLM
# ----------------------------------------------------------------------------
# Every hard fact in the dashboard (individual responses, tallies, means,
# distributions, people profiles) is extracted from the raw CSV/XLSX by this
# code. The analysis agents only contribute synthesis (themes, insights,
# commentary), and any quote text they reference is verified by QuoteGrounder.

def load_rows(path):
    """Read a survey export (CSV or XLSX) -> list of {header: str-value} rows."""
    if path.lower().endswith((".xlsx", ".xls")):
        import openpyxl
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
        vals = ws.iter_rows(values_only=True)
        headers = [re.sub(r"\s+", " ", str(h or "")).strip() for h in next(vals)]
        return [
            {h: ("" if v is None else str(v).strip()) for h, v in zip(headers, row)}
            for row in vals if any(v is not None and str(v).strip() for v in row)
        ]
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [
            {re.sub(r"\s+", " ", k or "").strip(): str(v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(f)
        ]


_META_RE = re.compile(r"^(id|start time|completion time|last modified.*|email.*|name)$", re.I)
_ADMIN_RE = re.compile(r"free lunch|order form|are you currently blocked|blocking you|retreat", re.I)
_OPT_PREFIX = re.compile(r"^\s*\d+\.\s*")


def _clean_option(v):
    return re.sub(r"\s+", " ", _OPT_PREFIX.sub("", str(v))).strip()


def _find_name_col(headers):
    for h in headers:
        if h.strip().lower() == "name":
            return h
    for h in headers:
        if "name" in h.strip().lower() and "project" not in h.lower():
            return h
    return None


def extract_survey(rows):
    """Deterministically classify each column and extract the real responses.

    Returns {"questions": [...], "freeText": [...], "excluded": [...],
             "respondents": [names]} — the ground truth the dashboard binds to.
    """
    if not rows:
        return None
    headers = list(rows[0].keys())
    name_col = _find_name_col(headers)
    respondents = [r.get(name_col, "").strip() for r in rows] if name_col else []

    questions, free_text, excluded = [], [], []
    total = len(rows)
    for h in headers:
        head_line = h.split("\n")[0].strip()
        if _META_RE.match(head_line):
            continue
        answered = [(r.get(name_col, "").strip() or "—", r[h]) for r in rows if r.get(h, "").strip()]
        if not answered:
            continue
        vals = [v for _, v in answered]
        skip_rate = whole(100 * (total - len(answered)) / total) or 0
        qtext = re.sub(r"\s+", " ", h).strip()
        is_admin = bool(_ADMIN_RE.search(h))

        numeric = [v for v in vals if re.fullmatch(r"\d+(\.\d+)?", v)]
        if len(numeric) == len(vals) and max(float(v) for v in vals) <= 10:
            scores = [float(v) for v in vals]
            dist = {}
            for s in scores:
                key = str(whole(s))
                dist[key] = dist.get(key, 0) + 1
            q = {
                "kind": "rating", "text": qtext,
                "scaleMax": 5 if max(scores) <= 5 else 10,
                "mean": round1(sum(scores) / len(scores)),
                "distribution": OrderedDict(sorted(dist.items(), key=lambda kv: int(kv[0]))),
                "skipRate": skip_rate, "responseCount": len(answered),
                "individualResponses": [{"respondent": nm, "value": float(v)} for nm, v in answered],
            }
        elif sum(1 for v in vals if ";" in v) >= max(1, len(vals) // 3):
            tally = OrderedDict()
            per_person = []
            for nm, v in answered:
                opts = [_clean_option(p) for p in v.split(";") if _clean_option(p)]
                for o in opts:
                    tally[o] = tally.get(o, 0) + 1
                per_person.append({"respondent": nm, "value": "; ".join(opts)})
            tally = OrderedDict(sorted(tally.items(), key=lambda kv: -kv[1]))
            q = {
                "kind": "multi-select", "text": qtext,
                "distribution": tally,
                "tally": [{"option": o, "count": c} for o, c in tally.items()],
                "skipRate": skip_rate, "responseCount": len(answered),
                "individualResponses": per_person,
            }
        else:
            cleaned = [(nm, _clean_option(v)) for nm, v in answered]
            counts = OrderedDict()
            for _, v in cleaned:
                counts[v] = counts.get(v, 0) + 1
            top = sorted(counts.values(), reverse=True)[:8]
            # long one-off "Other" answers don't disqualify a choice question —
            # only the repeated options must look like fixed options, and a
            # choice question must actually have repeats (else it's free text)
            short = all(len(o) <= 120 for o, c in counts.items() if c >= 2)
            if (short and max(counts.values()) >= 2 and len(cleaned) >= 5
                    and sum(top) >= 0.7 * len(cleaned) and len(counts) <= max(10, total // 4)):
                tally = OrderedDict(sorted(counts.items(), key=lambda kv: -kv[1]))
                q = {
                    "kind": "single-select", "text": qtext,
                    "distribution": tally,
                    "tally": [{"option": o, "count": c} for o, c in tally.items()],
                    "skipRate": skip_rate, "responseCount": len(answered),
                    "individualResponses": [{"respondent": nm, "value": v} for nm, v in cleaned],
                }
            else:
                if is_admin:
                    excluded.append({"text": qtext, "reason": "Admin/logistics question (auto-demoted)"})
                    continue
                free_text.append({
                    "text": qtext, "responseCount": len(answered),
                    "participationRate": whole(100 * len(answered) / total) or 0,
                    "responses": [{"respondent": nm, "text": v} for nm, v in answered],
                })
                continue
        if is_admin:
            excluded.append({"text": qtext, "reason": "Admin/logistics question (auto-demoted)"})
            continue
        questions.append(q)

    for i, q in enumerate(questions):
        q["id"] = f"q{i+1}"
    for i, q in enumerate(free_text):
        q["id"] = f"qt{i+1}"
    return {"questions": questions, "freeText": free_text,
            "excluded": excluded, "respondents": respondents}


# ----------------------------------------------------------------------------
# quote grounding — anti-hallucination gate against the raw survey data
# ----------------------------------------------------------------------------
# Every quote the agents emit (theme quotes, notable quotes, standouts) is
# checked against the respondent's actual cells in the raw data. Verbatim
# (after normalisation) passes; a near-match (agent fixed a typo / trimmed) is
# REPAIRED back to the real cell text; anything else is DROPPED and reported.
# This is the single chokepoint — the dashboard, result email, and recap video
# all render from consolidated.json.

def _norm_text(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class QuoteGrounder:
    def __init__(self, paths):
        self.sources = [os.path.basename(p) for p in paths]
        self.by_name = {}      # normalised respondent name -> [raw cell, ...]
        self.rows = []
        cells = []
        for path in paths:
            rows = load_rows(path)
            self.rows.extend(rows)
            for row in rows:
                name_col = _find_name_col(list(row.keys()))
                nm = _norm_text(row.get(name_col, "") if name_col else "")
                for v in row.values():
                    v = str(v or "").strip()
                    if v:
                        cells.append(v)
                        if nm:
                            self.by_name.setdefault(nm, []).append(v)
        self.global_corpus = " ||| ".join(_norm_text(c) for c in cells)
        self.checked = self.repaired = self.dropped = 0
        self.dropped_items = []

    def _corpus_for(self, name):
        cells = self.by_name.get(_norm_text(name))
        if cells:
            return cells, " ||| ".join(_norm_text(c) for c in cells)
        return None, self.global_corpus

    def ground(self, name, text):
        """Return text verbatim if traceable to the source data, the real cell
        text if it's a near-match (repair), or None if it can't be traced."""
        t = _norm_text(text)
        if not t:
            return text
        self.checked += 1
        cells, corpus = self._corpus_for(name)
        if t in corpus:
            return text
        # spliced excerpt ("..." joins, or non-adjacent sentences run together) —
        # keep only if EVERY substantial sentence is verbatim from this person
        parts = re.split(r"\.\.\.|…|(?<=[.!?])\s+", str(text))
        if len(parts) > 1:
            frags = [_norm_text(p) for p in parts if len(_norm_text(p)) >= 12]
            if frags and all(f in corpus for f in frags):
                return text
        # near-match against the respondent's own cells -> repair to the truth
        if cells:
            # same answer, silently edited (identical long opening) -> real full cell
            if len(t) >= 80:
                for c in cells:
                    if t[:80] in _norm_text(c):
                        self.repaired += 1
                        return c.strip()
            best = max(cells, key=lambda c: difflib.SequenceMatcher(None, t, _norm_text(c)).ratio())
            if difflib.SequenceMatcher(None, t, _norm_text(best)).ratio() >= 0.8:
                self.repaired += 1
                return best.strip()
        self.dropped += 1
        self.dropped_items.append({"name": str(name or ""), "text": str(text)[:120]})
        sys.stderr.write(f"[build-consolidated] DROPPED unverifiable quote ({name}): {str(text)[:80]!r}\n")
        return None

    def summary(self):
        return {
            "groundedAgainst": self.sources,
            "checked": self.checked,
            "repaired": self.repaired,
            "dropped": self.dropped,
            "droppedItems": self.dropped_items[:20],
        }


def ground_quote_obj(grounder, obj, key="text"):
    """Ground obj[key] in place; returns False if the quote must be dropped."""
    g = grounder.ground(obj.get("name") or obj.get("respondent"), obj.get(key, ""))
    if g is None:
        return False
    obj[key] = g
    if key != "text" and "text" in obj:
        obj["text"] = g
    return True


def whole(x):
    try:
        return int(round(float(x)))
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------
# data-first builders — real responses from the file, agent JSON for synthesis
# ----------------------------------------------------------------------------

def _agent_question_lut(*question_lists):
    lut = {}
    for qs in question_lists:
        for q in as_list(qs):
            if isinstance(q, dict):
                key = _norm_text(first(q, "text", "question", default=""))[:40]
                if key and key not in lut:
                    lut[key] = q
    return lut


def build_question_breakdown_from_data(extracted, quant):
    """questionBreakdown with responses/stats from the raw file; only the
    interpretive fields (commentary, flags, benchmark) come from the agent."""
    lut = _agent_question_lut(quant.get("ratingQuestions"), quant.get("choiceQuestions"))
    out = []
    for q in extracted["questions"]:
        a = lut.get(_norm_text(q["text"])[:40], {})
        entry = dict(q)
        entry["benchmark"] = first(a, "benchmark", default="")
        entry["flags"] = as_list(a.get("flags"))
        insight = first(a, "commentary", "insight", "headline", default="")
        entry["insight"] = insight
        entry["commentary"] = insight
        out.append(entry)
    return out


def build_free_text_from_data(extracted, qual):
    """freeTextQuestions with every response verbatim from the raw file; the
    agent only influences which responses are curated as 'most insightful'."""
    surfaced = _surfaced_quote_keys(qual)
    out = []
    for q in extracted["freeText"]:
        entry = dict(q)
        entry["curated"] = _curate(q["responses"], surfaced)
        entry["individualResponses"] = q["responses"]
        out.append(entry)
    return out


# ----------------------------------------------------------------------------
# questionBreakdown — ratings + choice questions
# (LEGACY fallback: used only when no raw survey file is available)
# ----------------------------------------------------------------------------

def build_question_breakdown(quant):
    out = []

    for q in as_list(quant.get("ratingQuestions")):
        if not isinstance(q, dict):
            continue
        responses = []
        for r in as_list(q.get("individualResponses")):
            nm = name_of(r)
            if not nm:
                continue
            responses.append({"respondent": nm, "value": first(r, "value", "score", "rating")})
        scale = q.get("scaleRange") or [1, 5]
        out.append({
            "id": first(q, "id", default=f"r{len(out)+1}"),
            "kind": "rating",
            "text": first(q, "text", "question", default=""),
            "scaleMax": (scale[1] if isinstance(scale, list) and len(scale) > 1 else 5),
            "mean": round1(q.get("mean")),
            "distribution": q.get("distribution") or {},
            "skipRate": whole(q.get("skipRate")) or 0,
            "responseCount": q.get("responseCount") or len(responses),
            "benchmark": first(q, "benchmark", default=""),
            "flags": as_list(q.get("flags")),
            "insight": first(q, "commentary", "insight", default=""),
            "commentary": first(q, "commentary", "insight", default=""),
            "individualResponses": responses,
        })

    for q in as_list(quant.get("choiceQuestions")):
        if not isinstance(q, dict):
            continue
        # tally -> distribution dict (option -> count), preserving order
        distribution = OrderedDict()
        for t in as_list(q.get("tally")):
            if isinstance(t, dict):
                opt = str(first(t, "option", "label", "name", default="")).strip()
                if opt:
                    distribution[opt] = whole(first(t, "count", "value", default=0)) or 0
        if not distribution and isinstance(q.get("distribution"), dict):
            distribution = q["distribution"]
        responses = []
        for r in as_list(q.get("individualResponses")):
            nm = name_of(r)
            if not nm:
                continue
            responses.append({"respondent": nm, "value": first(r, "value", "text", default="")})
        out.append({
            "id": first(q, "id", default=f"c{len(out)+1}"),
            "kind": first(q, "kind", default="single-select"),
            "text": first(q, "text", "question", default=""),
            "distribution": distribution,
            "tally": q.get("tally") or [],
            "skipRate": whole(q.get("skipRate")) or 0,
            "responseCount": q.get("responseCount") or len(responses),
            "flags": as_list(q.get("flags")),
            "insight": first(q, "headline", "insight", "commentary", default=""),
            "individualResponses": responses,
        })

    return out


# ----------------------------------------------------------------------------
# freeTextQuestions
# ----------------------------------------------------------------------------

_LOW_SIGNAL = {"n/a", "na", "none", "no", "nil", "nothing", "-", "—", "nope", "n/a not a dev"}


def _surfaced_quote_keys(qual):
    """Prefixes of every response the qualitative agent already surfaced as
    notable (standouts, notable quotes, theme quotes) — our 'AI-picked' signal."""
    keys = set()

    def add(t):
        t = re.sub(r"\s+", " ", str(t or "").strip().lower())
        if len(t) >= 12:
            keys.add(t[:60])
    for s in as_list(qual.get("standoutResponses")):
        add(first(s, "response", "text"))
    for q in as_list(qual.get("notableQuotes")):
        add(q.get("text"))
    for t in as_list(qual.get("themes")):
        for q in as_list(t.get("allQuotes")):
            add(q.get("text"))
        rq = t.get("representativeQuote")
        if isinstance(rq, dict):
            add(rq.get("text"))
    return keys


def _substance(txt):
    """Cheap opinion/insight score — length + opinion markers; 0 for filler."""
    t = txt.strip().lower()
    if t in _LOW_SIGNAL or len(t) < 12:
        return 0
    wc = len(re.findall(r"\w+", t))
    markers = ("but ", "however", "because", "should", "need", "wish", "annoying",
               "great", "love", "hate", "prefer", "issue", "bug", "problem",
               "better", "worse", "!", "painful", "awesome", "confusing")
    op = sum(t.count(m) for m in markers)
    return wc + op * 4


def _curate(responses, surfaced, want=6, cap=8):
    """Pick the most insightful/opinionated responses: agent-surfaced first, then
    by substance score. Returns a curated subset (the raw list stays available)."""
    curated, seen = [], set()

    def take(r):
        k = (r["respondent"], r["text"][:40])
        if k not in seen and _substance(r["text"]) > 0:
            seen.add(k)
            curated.append(r)
    for r in responses:  # agent-surfaced picks first
        key = re.sub(r"\s+", " ", r["text"].strip().lower())[:60]
        if key in surfaced:
            take(r)
    if len(curated) < want:  # top up by substance
        for r in sorted(responses, key=lambda r: _substance(r["text"]), reverse=True):
            take(r)
            if len(curated) >= want:
                break
    return curated[:cap]


def build_free_text(qual, grounder=None):
    out = []
    surfaced = _surfaced_quote_keys(qual)
    questions = first(qual, "questions", "freeTextQuestions", default=[])
    for q in as_list(questions):
        if not isinstance(q, dict):
            continue
        responses = []
        src = first(q, "individualResponses", "responses", default=[])
        for r in as_list(src):
            nm = name_of(r)
            txt = str(first(r, "text", "value", "response", default="") or "").strip()
            if not txt:
                continue
            if grounder is not None:
                txt = grounder.ground(nm, txt)
                if txt is None:
                    continue
            responses.append({"respondent": nm or "—", "text": txt})
        curated = _curate(responses, surfaced)
        out.append({
            "id": first(q, "id", default=f"qt{len(out)+1}"),
            "text": first(q, "text", "question", default=""),
            "responseCount": q.get("responseCount") or len(responses),
            "participationRate": whole(q.get("participationRate")) or 0,
            # `curated` = the insightful/opinionated picks the dashboard leads with;
            # `responses` = every raw response (behind a "Show all" toggle).
            "curated": curated,
            "responses": responses,
            "individualResponses": responses,
        })
    return out


# ----------------------------------------------------------------------------
# themes / notable quotes / standouts
# ----------------------------------------------------------------------------

def _question_text_lookup(free_text):
    lut = {}
    for q in free_text:
        lut[q.get("id")] = q.get("text", "")
    return lut


def build_themes(qual, free_text):
    qlut = _question_text_lookup(free_text)
    out = []
    for t in as_list(qual.get("themes")):
        if not isinstance(t, dict):
            continue
        appears_ids = as_list(first(t, "appearsInQuestions", "appearsIn", default=[]))
        appears_text = [qlut.get(i, i) for i in appears_ids]
        ctx_q = appears_text[0] if appears_text else ""

        def mk_quote(qobj):
            if not isinstance(qobj, dict):
                return None
            nm = name_of(qobj)
            return {
                "text": str(first(qobj, "text", "quote", default="")).strip(),
                "respondent": nm,
                "name": nm,
                "question": first(qobj, "question", default=ctx_q),
            }

        rep = mk_quote(t.get("representativeQuote")) or {"text": "", "respondent": "", "name": "", "question": ctx_q}
        all_quotes = [mk_quote(q) for q in as_list(t.get("allQuotes"))]
        all_quotes = [q for q in all_quotes if q and q["text"]]
        out.append({
            "id": first(t, "id", default=f"t{len(out)+1}"),
            "name": first(t, "name", default=""),
            "frequency": whole(first(t, "frequency", default=len(all_quotes))) or len(all_quotes),
            "frequencyPercent": whole(t.get("frequencyPercent")) or 0,
            "sentiment": first(t, "sentiment", default="neutral"),
            "intensity": first(t, "intensity", default=""),
            "appearsIn": appears_text,
            "representativeQuote": rep,
            "allQuotes": all_quotes,
            "actionability": first(t, "takeaway", "actionability", default=""),
            "importance": first(t, "importance", default="medium"),
        })
    return out


def build_notable_quotes(qual, theme_lut):
    out = []
    for q in as_list(qual.get("notableQuotes")):
        if not isinstance(q, dict):
            continue
        nm = name_of(q)
        out.append({
            "text": str(first(q, "text", "quote", default="")).strip(),
            "respondent": nm,
            "name": nm,
            "question": first(q, "question", default=""),
            "theme": theme_lut.get(q.get("theme"), q.get("theme", "")),
        })
    return [q for q in out if q["text"]]


def build_standouts(qual):
    out = []
    for s in as_list(qual.get("standoutResponses")):
        if not isinstance(s, dict):
            continue
        nm = name_of(s)
        resp = str(first(s, "response", "text", default="")).strip()
        out.append({
            "respondent": nm,
            "name": nm,
            "question": first(s, "question", default=""),
            "response": resp,
            "text": resp,
            "whyStandout": first(s, "whyStandout", "whySelected", "reason", default=""),
        })
    return [s for s in out if s["response"]]


# ----------------------------------------------------------------------------
# people — pivot per-question responses into per-person profiles
# ----------------------------------------------------------------------------

def build_people(question_breakdown, free_text, survey_label):
    people = {}

    def ensure(name):
        if name not in people:
            people[name] = {"name": name, "numericResponses": [], "textResponses": []}
        return people[name]

    for q in question_breakdown:
        qtext = q.get("text", "")
        if q.get("kind") == "rating":
            for r in q.get("individualResponses", []):
                nm = r.get("respondent")
                val = r.get("value")
                if not nm or val is None:
                    continue
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    continue
                ensure(nm)["numericResponses"].append(
                    {"question": qtext, "value": val, "surveyLabel": survey_label})
        else:
            # choice / categorical answers shown as text responses (not 1-5 scores)
            for r in q.get("individualResponses", []):
                nm = r.get("respondent")
                val = str(r.get("value") or "").strip()
                if not nm or not val:
                    continue
                ensure(nm)["textResponses"].append(
                    {"question": qtext, "text": val, "surveyLabel": survey_label})

    for q in free_text:
        qtext = q.get("text", "")
        for r in q.get("responses", []):
            nm = r.get("respondent")
            txt = r.get("text")
            if not nm or nm == "—" or not txt:
                continue
            ensure(nm)["textResponses"].append(
                {"question": qtext, "text": txt, "surveyLabel": survey_label})

    respondents = []
    for p in people.values():
        nums = [r["value"] for r in p["numericResponses"]]
        avg = round1(sum(nums) / len(nums)) if nums else None
        p["averageScore"] = avg
        p["responseCount"] = len(p["numericResponses"]) + len(p["textResponses"])
        p["flags"] = []
        respondents.append(p)

    # mechanical flags: highest / lowest average among those with numeric answers
    scored = [p for p in respondents if p["averageScore"] is not None]
    if scored:
        hi = max(scored, key=lambda p: p["averageScore"])
        lo = min(scored, key=lambda p: p["averageScore"])
        if hi["averageScore"] != lo["averageScore"]:
            hi["flags"].append("highest scorer")
            lo["flags"].append("most critical")
    if respondents:
        most = max(respondents, key=lambda p: p["responseCount"])
        if most["responseCount"] > 0:
            most["flags"].append("most-engaged")
    # light topic flags from text
    for p in respondents:
        blob = " ".join(r["text"].lower() for r in p["textResponses"])
        if re.search(r"subagent|daily driver|every day|power.?user", blob):
            p["flags"].append("power-user")
        if re.search(r"web (ui|interface|is better)|not convinced|skeptic|prefer the", blob):
            p["flags"].append("skeptic")

    respondents.sort(key=lambda p: p["name"].lower())
    return {"respondents": respondents}


# ----------------------------------------------------------------------------
# signals (redFlags) / adoption gaps / recommendations / hard truths
# ----------------------------------------------------------------------------

def build_red_flags(rf):
    out = []
    for s in as_list(rf.get("skeptics")):
        if not isinstance(s, dict):
            continue
        voices = ", ".join(as_list(s.get("voices")))
        out.append({
            "flag": first(s, "stance", "flag", default="Skeptic worth hearing"),
            "severity": "low",
            "evidence": first(s, "evidence", default=""),
            "prediction": first(s, "worthHearing", "prediction", default=""),
            "timeToAct": "Note in the rule" + (f" — {voices}" if voices else ""),
        })
    for g in as_list(rf.get("adoptionGaps")):
        if not isinstance(g, dict):
            continue
        out.append({
            "flag": first(g, "gap", "flag", default="Adoption gap"),
            "severity": "moderate",
            "evidence": first(g, "evidence", default=""),
            "prediction": first(g, "opportunity", "prediction", default=""),
            "timeToAct": "This quarter",
        })
    for c in as_list(rf.get("contentIssues")):
        if not isinstance(c, dict):
            continue
        out.append({
            "flag": first(c, "issue", "flag", default="Content issue"),
            "severity": "low",
            "evidence": first(c, "evidence", default=""),
            "prediction": first(c, "suggestion", "prediction", default=""),
            "timeToAct": "Next time this topic runs",
        })
    blockers = rf.get("blockers") or {}
    if isinstance(blockers, dict) and (blockers.get("count") or blockers.get("items")):
        cnt = whole(blockers.get("count")) or len(as_list(blockers.get("items")))
        if cnt:
            out.append({
                "flag": f"{cnt} blocked this week (scrum pulse)",
                "severity": "low",
                "evidence": first(blockers, "note", default="Surfaced from the 'are you blocked?' check — pass to leads."),
                "prediction": "Secondary to the topic; follow up in scrum.",
                "timeToAct": "This week",
            })
    return out


def build_adoption_gaps(rf):
    out = []
    for g in as_list(rf.get("adoptionGaps")):
        if not isinstance(g, dict):
            continue
        out.append({
            "gap": first(g, "gap", default=""),
            "evidence": first(g, "evidence", default=""),
            "opportunity": first(g, "opportunity", default=""),
        })
    return out


def build_recommendations(rf, sentiment):
    recs = rf.get("recommendations") or {}
    one_thing = sentiment.get("oneThing") or {}
    default_owners = {
        "immediate": "Free Lunch host",
        "shortTerm": "A team power-user",
        "strategic": "Rules owner",
    }

    def tier(key):
        items = []
        for r in as_list(recs.get(key)):
            if not isinstance(r, dict):
                continue
            items.append({
                "action": first(r, "action", default=""),
                "owner": first(r, "owner", default=default_owners.get(key, "TBD")),
                "rationale": first(r, "rationale", default=""),
                "successMetric": first(r, "successMetric", "impact", default=""),
            })
        return items

    immediate = tier("immediate")
    short_term = tier("shortTerm")
    strategic = tier("strategic")
    # backstop: if short-term empty but sentiment surfaced a "one thing", use it
    if not short_term and one_thing.get("action"):
        short_term = [{
            "action": one_thing.get("action", ""),
            "owner": default_owners["shortTerm"],
            "rationale": one_thing.get("rationale", ""),
            "successMetric": one_thing.get("impact", ""),
        }]
    return {"immediate": immediate, "shortTerm": short_term, "strategic": strategic}


def build_hard_truths(rf, sentiment):
    truths = []
    ht = first(rf, "honestTake", default="")
    if isinstance(ht, str) and ht.strip():
        truths.append(ht.strip())
    depth = (sentiment.get("adoptionDepth") or {}).get("note")
    if isinstance(depth, str) and depth.strip() and len(truths) < 2:
        truths.append(depth.strip())
    return truths[:2]


# ----------------------------------------------------------------------------
# overview synthesis — exec summary, verdict, grade, key metrics
# ----------------------------------------------------------------------------

def _grade_from_mean(mean, scale_max=5):
    if mean is None:
        return "B"
    pct = mean / (scale_max or 5)
    if pct >= 0.9:
        return "A"
    if pct >= 0.82:
        return "A-"
    if pct >= 0.74:
        return "B"
    if pct >= 0.6:
        return "C"
    if pct >= 0.5:
        return "D"
    return "F"


def build_overview(quant, qual, sentiment, rf, question_breakdown):
    reception = quant.get("topicReception") or {}
    narrative = qual.get("overallNarrative") or {}
    rule_mean = round1(first(reception, "ruleRating", default=None))
    if rule_mean is None:
        ratings = [q["mean"] for q in question_breakdown if q.get("kind") == "rating" and q.get("mean")]
        rule_mean = round1(sum(ratings) / len(ratings)) if ratings else None

    bullets = []
    for cand in [
        reception.get("verdict"),
        narrative.get("headline"),
        reception.get("adoptionHeadline"),
        narrative.get("keyTheme"),
        narrative.get("emergingPractice"),
        (sentiment.get("topicStance") or {}).get("insight"),
    ]:
        if isinstance(cand, str) and cand.strip() and cand.strip() not in bullets:
            bullets.append(cand.strip())
    bullets = bullets[:5]

    grade = _grade_from_mean(rule_mean)
    verdict = first(reception, "verdict", default="") or first(rf, "honestTake", default="")

    return {
        "bullets": bullets,
        "overallVerdict": verdict,
        "overallGrade": grade,
    }


def build_key_metrics(quant, question_breakdown, rf):
    """Headline metric cards. Deliberately led by the OPINION + ADOPTION signal —
    the video/rule content ratings are NOT featured here (they rarely carry the
    insight and would just be two near-identical 4.x/5 numbers). Those still live
    in the Responses tab. Cards: top pick, adoption frontier, task value, + one
    more opinion signal (else response count)."""
    metrics = []
    reception = quant.get("topicReception") or {}

    # 1. Top pick from the first choice question (what the team actually chose)
    first_choice_text = None
    for q in question_breakdown:
        if q.get("kind") in ("single-select", "multi-select") and q.get("distribution"):
            top = max(q["distribution"].items(), key=lambda kv: kv[1])
            first_choice_text = q.get("text", "")[:60]
            metrics.append({"label": "Top pick", "value": top[0], "status": "good",
                            "context": first_choice_text})
            break

    # 2. Adoption frontier — where uptake is thin (first gap %)
    gaps = as_list(rf.get("adoptionGaps"))
    if gaps and isinstance(gaps[0], dict):
        ev = gaps[0].get("evidence", "")
        m = re.search(r"(\d+\s*%)", ev)
        metrics.append({"label": "Adoption frontier", "value": m.group(1) if m else "See gaps",
                        "status": "watch", "context": gaps[0].get("gap", "")[:60]})

    # 3. Task value — the one content rating that reflects the exercise's worth
    task_value = round1(reception.get("taskValueRating"))
    if task_value is not None:
        metrics.append({"label": "Task value", "value": f"{task_value}/5",
                        "status": "good" if task_value >= 4 else "watch"})

    # 4. A second opinion signal from another choice question, else response count
    if len(metrics) < 4:
        for q in question_breakdown:
            if (q.get("kind") in ("single-select", "multi-select") and q.get("distribution")
                    and q.get("text", "")[:60] != first_choice_text):
                top = max(q["distribution"].items(), key=lambda kv: kv[1])
                metrics.append({"label": "Also notable", "value": top[0], "status": "good",
                                "context": q.get("text", "")[:60]})
                break
    if len(metrics) < 4:
        rc = whole(first(quant.get("metadata") or {}, "totalResponses", "responseCount", default=None))
        if rc:
            metrics.append({"label": "Responses", "value": str(rc), "status": "good",
                            "context": "100% of the team"})
    return metrics[:4]


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis_dir")
    ap.add_argument("--survey-name", default=None)
    ap.add_argument("--topic", default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--rule-url", default=None)
    ap.add_argument("--focus", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--data", default=None,
                    help="raw survey CSV(s) to verify quotes against "
                         "(default: *.csv next to the analysis dir)")
    ap.add_argument("--no-photos", action="store_true",
                    help="skip SSW.People profile-photo resolution (offline/local runs)")
    args = ap.parse_args()

    d = args.analysis_dir
    quant = load(os.path.join(d, "quantitative.json"))
    qual = load(os.path.join(d, "qualitative.json"))
    sentiment = load(os.path.join(d, "sentiment.json"))
    rf = load(os.path.join(d, "red-flags.json"))

    if not (quant or qual):
        sys.stderr.write("[build-consolidated] error: no quantitative/qualitative input found\n")
        sys.exit(1)

    qmeta = quant.get("metadata") or {}
    topic = args.topic or first(qmeta, "topic", default=None) or first(qual.get("metadata") or {}, "topic", default="Survey")
    survey_name = args.survey_name or topic
    survey_label = survey_name

    # Source of truth: the raw survey file. Bulk data (individual responses,
    # tallies, means, people) is extracted from it in code — no LLM in the loop.
    parent = os.path.dirname(os.path.abspath(d))
    data_paths = [args.data] if args.data else sorted(
        glob.glob(os.path.join(parent, "*.csv")) + glob.glob(os.path.join(parent, "*.xlsx")))
    grounder = QuoteGrounder(data_paths) if data_paths else None
    extracted = extract_survey(grounder.rows) if grounder else None

    if extracted and (extracted["questions"] or extracted["freeText"]):
        question_breakdown = build_question_breakdown_from_data(extracted, quant)
        free_text = build_free_text_from_data(extracted, qual)
    else:
        sys.stderr.write(
            "[build-consolidated] WARNING: no raw survey file (*.csv/*.xlsx) found next to "
            "the analysis dir — falling back to UNVERIFIED agent-emitted bulk data. "
            "Fix the data path; do not ship this.\n")
        question_breakdown = build_question_breakdown(quant)
        free_text = build_free_text(qual, grounder)
    themes = build_themes(qual, free_text)
    theme_lut = {t["id"]: t["name"] for t in themes}
    notable = build_notable_quotes(qual, theme_lut)
    standouts = build_standouts(qual)
    if grounder is not None:
        for t in themes:
            t["allQuotes"] = [q for q in t["allQuotes"] if ground_quote_obj(grounder, q)]
            rep = t.get("representativeQuote") or {}
            if rep.get("text") and not ground_quote_obj(grounder, rep):
                t["representativeQuote"] = (t["allQuotes"][0] if t["allQuotes"]
                                            else {"text": "", "respondent": "", "name": "", "question": ""})
        notable = [q for q in notable if ground_quote_obj(grounder, q)]
        standouts = [s for s in standouts if ground_quote_obj(grounder, s, key="response")]
    people = build_people(question_breakdown, free_text, survey_label)

    # Resolve each respondent's name to an SSW.People profile photo (best-effort;
    # unresolved names -> None -> renderers show initials). One central map keyed
    # by display name; renderers (dashboard + video plan) look names up in it.
    quote_names = (
        [q.get("name") for t in themes for q in t.get("allQuotes", [])]
        + [t.get("representativeQuote", {}).get("name") for t in themes]
        + [q.get("name") for q in notable]
        + [s.get("name") for s in standouts]
    )
    all_names = [p["name"] for p in people["respondents"]] + quote_names
    photos = {} if args.no_photos else ssw_people.build_photo_map(all_names)
    for p in people["respondents"]:
        p["photoUrl"] = photos.get(p["name"])
    resolved = sum(1 for v in photos.values() if v)

    # sentiment overview
    stance = sentiment.get("topicStance") or {}
    spectrum = stance.get("spectrum") or {}
    alignment = sentiment.get("alignment") or {}
    sentiment_overview = {
        "spectrumScore": round1(spectrum.get("score")),
        "spectrumLabel": first(spectrum, "label", default=""),
        "dominantStance": first(stance, "dominantStance", default=""),
        "secondaryStance": first(stance, "secondaryStance", default=""),
        "emotionalBreakdown": extract_stance_breakdown(sentiment),
        "candorLevel": "high",
        "quantQualDissonance": whole(first(alignment, "coolDissonance", default=0)) or 0,
        "keyInsight": first(stance, "insight", default=""),
        "alignment": alignment,
        "adoptionDepth": sentiment.get("adoptionDepth") or {},
    }

    overview = build_overview(quant, qual, sentiment, rf, question_breakdown)

    if extracted:
        response_count = len({n for n in extracted["respondents"] if n}) or len(grounder.rows)
    else:
        response_count = whole(first(qmeta, "totalResponses", "responseCount", default=None))
    if not response_count:
        names = {r["respondent"] for q in question_breakdown for r in q.get("individualResponses", [])}
        names |= {p["name"] for p in people["respondents"]}
        response_count = len(names)

    consolidated = OrderedDict()
    consolidated["metadata"] = {
        "surveyName": survey_name,
        "topic": topic,
        "ruleUrl": args.rule_url or first(qmeta, "ruleUrl", default=None),
        "ruleTitle": first(qmeta, "ruleTitle", default=None),
        # the weekly video the team was asked to watch + rate {title, url}
        "videoWatched": qmeta.get("videoWatched") or None,
        "responseCount": response_count,
        "completionRate": whole(first(qmeta, "completionRate", default=100)) or 100,
        "dateRange": args.date or "",
        "qualityScore": 90,
        "focusArea": args.focus,
        "surveyGroups": None,
    }
    consolidated["executiveSummary"] = {
        "bullets": overview["bullets"],
        "overallVerdict": overview["overallVerdict"],
    }
    consolidated["overallGrade"] = overview["overallGrade"]
    consolidated["focusSummary"] = (
        {"summary": args.focus} if args.focus else None
    )
    consolidated["keyMetrics"] = build_key_metrics(quant, question_breakdown, rf)
    consolidated["questionBreakdown"] = question_breakdown
    consolidated["freeTextQuestions"] = free_text
    consolidated["themes"] = themes
    consolidated["notableQuotes"] = notable
    consolidated["standoutResponses"] = standouts
    consolidated["sentimentOverview"] = sentiment_overview
    consolidated["people"] = people
    consolidated["photos"] = photos
    consolidated["redFlags"] = build_red_flags(rf)
    consolidated["adoptionGaps"] = build_adoption_gaps(rf)
    consolidated["recommendations"] = build_recommendations(rf, sentiment)
    consolidated["hardTruths"] = build_hard_truths(rf, sentiment)
    excluded_questions = extracted["excluded"] if extracted else as_list(quant.get("excludedQuestions"))
    consolidated["excludedQuestions"] = excluded_questions
    consolidated["crossSurveySynthesis"] = None
    consolidated["questionCoverageReport"] = {
        "numericQuestions": sum(1 for q in question_breakdown if q.get("kind") == "rating"),
        "choiceQuestions": sum(1 for q in question_breakdown if q.get("kind") != "rating"),
        "freeTextQuestions": len(free_text),
        "excludedQuestions": len(excluded_questions),
        "peopleProfiles": len(people["respondents"]),
    }
    consolidated["consolidationNotes"] = {
        "assembledBy": "build-consolidated.py (deterministic)",
        "bulkDataSource": ("raw survey file: " + ", ".join(grounder.sources)) if extracted
                          else "agent JSON (UNVERIFIED — no raw survey file found)",
        "dataHandlingActions": [
            "Excluded email addresses (never carried from agent outputs)",
            "Demoted logistics questions",
            f"Assembled {len(people['respondents'])} people profiles",
        ],
        "qualityScore": 90,
        "quoteVerification": grounder.summary() if grounder else {"status": "SKIPPED — no raw survey file found"},
    }

    out_path = args.out or os.path.join(d, "consolidated.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=2, ensure_ascii=False)

    print(f"[build-consolidated] wrote {out_path}")
    if extracted:
        print(f"  bulk data: extracted from {', '.join(grounder.sources)} "
              f"({response_count} respondents) — no LLM in the data path")
    else:
        print("  bulk data: LEGACY agent JSON (no raw survey file found) — UNVERIFIED")
    if grounder:
        print(f"  quote verification: {grounder.checked} checked, "
              f"{grounder.repaired} repaired to source text, {grounder.dropped} dropped")
    print(f"  questions: {len(question_breakdown)} structured, {len(free_text)} free-text")
    print(f"  themes: {len(themes)}  people: {len(people['respondents'])}  "
          f"signals: {len(consolidated['redFlags'])}  responses: {response_count}")
    if not args.no_photos:
        print(f"  photos: resolved {resolved}/{len(photos)} names to SSW profile photos")


if __name__ == "__main__":
    main()
