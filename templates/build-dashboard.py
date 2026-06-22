#!/usr/bin/env python3
"""
build-dashboard.py — deterministic dashboard renderer for Chewing the Fat surveys.

Renders the multi-tab HTML dashboard from consolidated.json + the template, the
same way generate-slides.py renders the PPTX. Replaces having the LLM generate
~hundreds of Alpine.js cards as output tokens (which does not scale — a
79-respondent People tab alone is thousands of lines of HTML).

Usage:
  python3 build-dashboard.py <consolidated.json> <template.html> <out/index.html>

The card markup matches the patterns documented inline in the template
(Alpine.js x-data cards, baked search indexes, score bars, severity badges).
"""

import html
import json
import re
import sys


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def esc(s):
    return html.escape(str(s if s is not None else ""))


def sidx(*parts):
    """Baked, attribute-safe lowercase search index (quotes stripped)."""
    text = " ".join(str(p) for p in parts if p)
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def score_class(pct):
    if pct >= 80:
        return "score-high"
    if pct >= 60:
        return "score-medium"
    return "score-low"


def initials(name):
    parts = [p for p in re.split(r"\s+", str(name).strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def paginated_responses(items, render_item, noun="responses"):
    """First 20 visible, the rest behind a Show-more (Alpine showAll)."""
    head = items[:20]
    tail = items[20:]
    html_parts = [render_item(it) for it in head]
    if tail:
        html_parts.append(
            '<template x-if="!showAll">'
            f'<button class="show-more-btn" @click="showAll = true">Show {len(tail)} more {noun}</button>'
            '</template>'
        )
        html_parts.append(
            '<template x-if="showAll">' + "".join(render_item(it) for it in tail) + '</template>'
        )
    return "".join(html_parts)


# ---------------------------------------------------------------------------
# Overview tab
# ---------------------------------------------------------------------------

def render_key_metrics(metrics):
    cards = []
    for m in metrics or []:
        status = m.get("status", "")
        value_color = "text-ssw-charcoal"
        if status == "good":
            value_color = "text-green-600"
        elif status in ("watch", "warning"):
            value_color = "text-amber-600"
        elif status in ("bad", "critical"):
            value_color = "text-ssw-red"
        ctx = m.get("context")
        cards.append(
            '<div class="bg-white rounded-xl shadow-sm ssw-card p-4">'
            f'<p class="text-xs text-ssw-gray-500 font-semibold uppercase tracking-wide">{esc(m.get("label"))}</p>'
            f'<p class="text-2xl font-bold {value_color} mt-1">{esc(m.get("value"))}</p>'
            + (f'<p class="text-xs text-ssw-gray-400 mt-1">{esc(ctx)}</p>' if ctx else "")
            + '</div>'
        )
    return "".join(cards)


def render_exec_summary(bullets):
    if not bullets:
        return '<li class="text-ssw-gray-400">No summary available.</li>'
    return "".join(
        '<li class="flex items-start">'
        '<span class="text-ssw-red mr-2 font-bold">•</span>'
        f'<span>{esc(b)}</span></li>'
        for b in bullets
    )


def render_focus_summary(focus):
    if not focus:
        return ""
    summary = focus.get("summary") if isinstance(focus, dict) else str(focus)
    if not summary:
        return ""
    return (
        '<section class="bg-amber-50 border-l-4 border-amber-400 rounded-r-xl p-6 mb-6">'
        '<h2 class="text-lg text-ssw-charcoal mb-2 font-bold">🎯 Focus Area</h2>'
        f'<p class="text-ssw-charcoal">{esc(summary)}</p>'
        '</section>'
    )


def render_standouts(standouts):
    if not standouts:
        return ""
    cards = []
    for s in standouts:
        name = s.get("name") or s.get("respondent") or "Anonymous"
        why = s.get("whyStandout") or "Notable"
        q = s.get("question")
        resp = s.get("response") or s.get("text") or ""
        cards.append(
            '<div class="standout-card mb-4">'
            '<div class="flex items-center gap-2 mb-2 flex-wrap">'
            f'<span class="font-semibold text-ssw-charcoal">{esc(name)}</span>'
            f'<span class="standout-badge">{esc(why)}</span></div>'
            + (f'<p class="text-xs text-ssw-gray-500 mb-1">Answering: &ldquo;{esc(q)}&rdquo;</p>' if q else "")
            + f'<blockquote class="quote-block">&ldquo;{esc(resp)}&rdquo;</blockquote>'
            '</div>'
        )
    return (
        '<section class="bg-white rounded-xl shadow-sm ssw-card p-6 mb-6">'
        '<h2 class="text-lg text-ssw-charcoal mb-4">💡 Standout Responses</h2>'
        + "".join(cards) + '</section>'
    )


def render_hard_truths(truths):
    if not truths:
        return '<p class="text-ssw-gray-400">No hard truths surfaced — the topic landed cleanly.</p>'
    return "".join(
        '<div class="flex items-start">'
        '<span class="mr-2">⚠️</span>'
        f'<p class="text-ssw-charcoal">{esc(t)}</p></div>'
        for t in truths
    )


# ---------------------------------------------------------------------------
# Responses tab — question cards
# ---------------------------------------------------------------------------

def _rating_response_item(r):
    return (
        '<div class="response-item flex items-center justify-between gap-3">'
        f'<span class="text-ssw-charcoal">{esc(r.get("respondent"))}</span>'
        f'<span class="font-bold text-ssw-charcoal">{esc(r.get("value"))}</span></div>'
    )


def _text_response_item(r):
    return (
        '<div class="response-item">'
        f'<p class="font-semibold text-ssw-charcoal text-xs mb-0.5">{esc(r.get("respondent"))}</p>'
        f'<p class="text-ssw-gray-600">{esc(r.get("text") or r.get("value"))}</p></div>'
    )


def render_distribution_minichart(distribution, ordered_keys=None):
    if not distribution:
        return ""
    keys = ordered_keys or list(distribution.keys())
    counts = [distribution.get(k, 0) or 0 for k in keys]
    mx = max(counts) if counts else 0
    if mx <= 0:
        return ""
    segs = []
    for k, c in zip(keys, counts):
        h = max(8, int(c / mx * 100))
        segs.append(
            f'<div class="distribution-bar-segment" style="height:{h}%" title="{esc(k)}: {c}"></div>'
        )
    return f'<div class="distribution-bar mb-3">{"".join(segs)}</div>'


def render_rating_card(q):
    text = q.get("text", "")
    mean = q.get("mean")
    scale = q.get("scaleMax") or 5
    pct = (float(mean) / scale * 100) if mean else 0
    cls = score_class(pct)
    flags = q.get("flags") or []
    flag_html = "".join(
        f'<span class="flag-badge">{esc(f if isinstance(f, str) else f.get("text", f))}</span>'
        for f in flags
    )
    responses = q.get("individualResponses") or []
    skip = q.get("skipRate", 0)
    rc = q.get("responseCount", len(responses))
    keys = [str(i) for i in range(1, int(scale) + 1)]
    idx = sidx(text, q.get("insight"), *[str(f) for f in flags])

    body = (
        '<template x-if="open"><div class="question-card-body p-4">'
        + (f'<p class="text-sm text-ssw-gray-600 mb-3">{esc(q.get("insight") or q.get("commentary"))}</p>'
           if (q.get("insight") or q.get("commentary")) else "")
        + render_distribution_minichart(q.get("distribution"), keys)
        + '<div class="flex flex-wrap gap-4 text-xs text-ssw-gray-500 mb-3">'
        + f'<span>Skip rate: {esc(skip)}%</span>'
        + f'<span>Responses: {esc(rc)}</span>'
        + (f'<span>Benchmark: {esc(q.get("benchmark"))}</span>' if q.get("benchmark") else "")
        + '</div>'
        + '<h4 class="text-sm font-semibold text-ssw-charcoal mt-4 mb-2">Individual Responses</h4>'
        + '<div class="response-list">'
        + paginated_responses(responses, _rating_response_item)
        + '</div></div></template>'
    )

    return (
        f'<div x-data="{{ open: false, showAll: false }}" '
        '@expand-all.window="open = true" @collapse-all.window="open = false" '
        f'x-show="!searchQuery || \'{idx}\'.includes(searchQuery.toLowerCase())" '
        'class="bg-white rounded-lg border border-ssw-gray-200 overflow-hidden">'
        '<div class="question-card-header p-4 flex items-center justify-between" @click="open = !open">'
        '<div class="flex-1">'
        f'<p class="font-semibold text-ssw-charcoal text-sm">Q: {esc(text)}</p>'
        '<div class="flex items-center gap-3 mt-2 flex-wrap">'
        f'<div class="score-bar flex-1 max-w-xs"><div class="score-bar-fill {cls}" style="width: {pct:.0f}%"></div></div>'
        f'<span class="text-sm font-bold text-ssw-charcoal">{esc(mean)}/{esc(scale)}</span>'
        f'{flag_html}</div></div>'
        '<span class="chevron-icon ml-3 text-ssw-gray-400" :class="open && \'open\'">▼</span>'
        '</div>' + body + '</div>'
    )


def render_choice_card(q):
    text = q.get("text", "")
    kind = q.get("kind", "single-select")
    dist = q.get("distribution") or {}
    responses = q.get("individualResponses") or []
    rc = q.get("responseCount", len(responses))
    items = sorted(dist.items(), key=lambda kv: kv[1], reverse=True)
    top = items[0][0] if items else "—"
    mx = items[0][1] if items else 0
    idx = sidx(text, kind, q.get("insight"), *[k for k, _ in items])

    bars = []
    for opt, cnt in items:
        w = int(cnt / mx * 100) if mx else 0
        pctv = int(cnt / rc * 100) if rc else 0
        bars.append(
            '<div class="mb-2">'
            '<div class="flex items-center justify-between text-xs text-ssw-charcoal mb-0.5">'
            f'<span>{esc(opt)}</span><span class="font-semibold">{cnt} ({pctv}%)</span></div>'
            f'<div class="score-bar"><div class="score-bar-fill score-medium" style="width: {w}%"></div></div>'
            '</div>'
        )

    body = (
        '<template x-if="open"><div class="question-card-body p-4">'
        + (f'<p class="text-sm text-ssw-gray-600 mb-3">{esc(q.get("insight"))}</p>' if q.get("insight") else "")
        + '<h4 class="text-sm font-semibold text-ssw-charcoal mb-2">Option tally</h4>'
        + "".join(bars)
        + '<h4 class="text-sm font-semibold text-ssw-charcoal mt-4 mb-2">Individual Responses</h4>'
        + '<div class="response-list">'
        + paginated_responses(responses, _text_response_item)
        + '</div></div></template>'
    )

    return (
        f'<div x-data="{{ open: false, showAll: false }}" '
        '@expand-all.window="open = true" @collapse-all.window="open = false" '
        f'x-show="!searchQuery || \'{idx}\'.includes(searchQuery.toLowerCase())" '
        'class="bg-white rounded-lg border border-ssw-gray-200 overflow-hidden">'
        '<div class="question-card-header p-4 flex items-center justify-between" @click="open = !open">'
        '<div class="flex-1">'
        f'<p class="font-semibold text-ssw-charcoal text-sm">Q: {esc(text)}</p>'
        '<div class="flex items-center gap-3 mt-2 flex-wrap">'
        f'<span class="flag-badge">{esc(kind)}</span>'
        f'<span class="text-xs text-ssw-gray-500">Top: {esc(top)} • {len(items)} options</span>'
        '</div></div>'
        '<span class="chevron-icon ml-3 text-ssw-gray-400" :class="open && \'open\'">▼</span>'
        '</div>' + body + '</div>'
    )


def render_freetext_card(q):
    text = q.get("text", "")
    responses = q.get("responses") or q.get("individualResponses") or []
    rc = q.get("responseCount", len(responses))
    idx = sidx(text, "free text", *[r.get("respondent", "") for r in responses[:10]])

    body = (
        '<template x-if="open"><div class="question-card-body p-4">'
        '<div class="response-list">'
        + paginated_responses(responses, _text_response_item)
        + '</div></div></template>'
    )

    return (
        f'<div x-data="{{ open: false, showAll: false }}" '
        '@expand-all.window="open = true" @collapse-all.window="open = false" '
        f'x-show="!searchQuery || \'{idx}\'.includes(searchQuery.toLowerCase())" '
        'class="bg-white rounded-lg border border-ssw-gray-200 overflow-hidden">'
        '<div class="question-card-header p-4 flex items-center justify-between" @click="open = !open">'
        '<div class="flex-1">'
        f'<p class="font-semibold text-ssw-charcoal text-sm">Q: {esc(text)}</p>'
        '<div class="flex items-center gap-3 mt-2">'
        '<span class="flag-badge">Free Text</span>'
        f'<span class="text-xs text-ssw-gray-500">{esc(rc)} responses</span>'
        '</div></div>'
        '<span class="chevron-icon ml-3 text-ssw-gray-400" :class="open && \'open\'">▼</span>'
        '</div>' + body + '</div>'
    )


def render_question_breakdown(consolidated):
    out = []
    for q in consolidated.get("questionBreakdown") or []:
        if q.get("kind") == "rating":
            out.append(render_rating_card(q))
        else:
            out.append(render_choice_card(q))
    free_text = consolidated.get("freeTextQuestions") or []
    if free_text:
        out.append(
            '<div class="survey-group-header mt-6"><h3>Free-Text Questions</h3>'
            f'<span class="survey-group-count">{len(free_text)} questions</span></div>'
        )
        for q in free_text:
            out.append(render_freetext_card(q))
    return "".join(out)


# ---------------------------------------------------------------------------
# Themes tab
# ---------------------------------------------------------------------------

def _sentiment_class(s):
    s = (s or "").lower()
    if "pos" in s:
        return "theme-positive"
    if "neg" in s:
        return "theme-negative"
    if "mix" in s:
        return "theme-mixed"
    return "theme-neutral"


def render_sentiment_overview(so):
    if not so:
        return '<p class="text-ssw-gray-300">No stance data.</p>'
    label = so.get("spectrumLabel") or so.get("dominantStance") or "—"
    insight = so.get("keyInsight") or ""
    dom = so.get("dominantStance") or ""
    sec = so.get("secondaryStance") or ""
    chips = []
    if dom:
        chips.append(f'<span>Dominant: <strong>{esc(dom)}</strong></span>')
    if sec:
        chips.append(f'<span>Secondary: <strong>{esc(sec)}</strong></span>')
    if so.get("spectrumScore") is not None:
        chips.append(f'<span>Stance score: <strong>{esc(so.get("spectrumScore"))}</strong></span>')
    return (
        f'<p class="text-2xl font-bold">{esc(label)}</p>'
        + (f'<p class="text-ssw-gray-300 mt-2">{esc(insight)}</p>' if insight else "")
        + ('<div class="flex flex-wrap gap-6 mt-3 text-sm text-ssw-gray-300">' + "".join(chips) + '</div>'
           if chips else "")
    )


def render_theme_cards(themes):
    cards = []
    for t in themes or []:
        name = t.get("name", "")
        freq = t.get("frequency", 0)
        pct = t.get("frequencyPercent", 0)
        rep = t.get("representativeQuote") or {}
        rep_name = rep.get("name") or rep.get("respondent") or ""
        all_quotes = t.get("allQuotes") or []
        appears = ", ".join(t.get("appearsIn") or []) or "—"
        idx = sidx(name, rep.get("text"), rep_name, *[q.get("name") or q.get("respondent") for q in all_quotes[:8]])

        quote_items = []
        for q in all_quotes:
            qn = q.get("name") or q.get("respondent") or ""
            qq = q.get("question")
            quote_items.append(
                '<div class="response-item">'
                + (f'<p class="people-question-label">Answering: &ldquo;{esc(qq)}&rdquo;</p>' if qq else "")
                + f'<blockquote class="quote-block text-sm">&ldquo;{esc(q.get("text"))}&rdquo;</blockquote>'
                + f'<p class="quote-attribution">— {esc(qn)}</p></div>'
            )

        body = (
            '<template x-if="open"><div class="question-card-body pt-4 mt-3">'
            '<div class="flex flex-wrap gap-3 text-xs text-ssw-gray-500 mb-3">'
            + (f'<span>Actionability: {esc(t.get("actionability"))}</span>' if t.get("actionability") else "")
            + f'<span>Appears in: {esc(appears)}</span></div>'
            + f'<h4 class="text-sm font-semibold text-ssw-charcoal mb-2">All Quotes ({len(all_quotes)})</h4>'
            + '<div class="response-list space-y-2">' + "".join(quote_items) + '</div>'
            + '</div></template>'
        )

        cards.append(
            f'<div x-data="{{ open: false }}" '
            '@expand-all.window="open = true" @collapse-all.window="open = false" '
            f'x-show="!searchQuery || \'{idx}\'.includes(searchQuery.toLowerCase())" '
            f'class="theme-card {_sentiment_class(t.get("sentiment"))} bg-white rounded-lg p-4">'
            '<div class="question-card-header flex items-center justify-between" @click="open = !open">'
            '<div class="flex-1">'
            '<div class="flex items-center gap-2 flex-wrap">'
            f'<h3 class="font-semibold text-ssw-charcoal">{esc(name)}</h3>'
            f'<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-ssw-gray-100">{esc(freq)} responses ({esc(pct)}%)</span>'
            '</div>'
            + (f'<p class="quote-block text-sm mt-2">&ldquo;{esc(rep.get("text"))}&rdquo;</p>' if rep.get("text") else "")
            + (f'<p class="quote-attribution">— {esc(rep_name)}</p>' if rep_name else "")
            + '</div>'
            '<span class="chevron-icon ml-3 text-ssw-gray-400" :class="open && \'open\'">▼</span>'
            '</div>' + body + '</div>'
        )
    return "".join(cards)


def render_notable_quotes(quotes):
    if not quotes:
        return '<p class="text-ssw-gray-400">No notable quotes.</p>'
    out = []
    for q in quotes:
        nm = q.get("name") or q.get("respondent") or ""
        theme = q.get("theme")
        attr = f'— {esc(nm)}' + (f' <span class="text-ssw-gray-400">· {esc(theme)}</span>' if theme else "")
        out.append(
            '<div class="border-l-4 border-ssw-gray-300 pl-4">'
            + (f'<p class="text-xs text-ssw-gray-500 mb-1">Answering: &ldquo;{esc(q.get("question"))}&rdquo;</p>'
               if q.get("question") else "")
            + f'<blockquote class="quote-block">&ldquo;{esc(q.get("text"))}&rdquo;</blockquote>'
            + f'<p class="quote-attribution">{attr}</p></div>'
        )
    return "".join(out)


# ---------------------------------------------------------------------------
# People tab
# ---------------------------------------------------------------------------

def render_people_cards(people):
    respondents = (people or {}).get("respondents") or []
    cards = []
    for p in respondents:
        name = p.get("name", "")
        avg = p.get("averageScore")
        rc = p.get("responseCount", 0)
        flags = p.get("flags") or []
        pct = (float(avg) / 5 * 100) if avg else 0
        cls = score_class(pct)
        flag_html = "".join(f'<span class="flag-badge">{esc(f)}</span>' for f in flags)
        idx = sidx(name)

        nums = p.get("numericResponses") or []
        texts = p.get("textResponses") or []

        num_items = []
        for r in nums:
            v = r.get("value")
            vpct = (float(v) / 5 * 100) if v is not None else 0
            num_items.append(
                '<div class="response-item">'
                f'<p class="people-question-label">{esc(r.get("question"))}</p>'
                '<div class="flex items-center gap-2">'
                f'<div class="score-bar" style="width:100px"><div class="score-bar-fill {score_class(vpct)}" style="width:{vpct:.0f}%"></div></div>'
                f'<span class="text-xs font-bold text-ssw-charcoal">{esc(v)}/5</span></div></div>'
            )
        text_items = []
        for r in texts:
            text_items.append(
                '<div class="response-item">'
                f'<p class="people-question-label">{esc(r.get("question"))}</p>'
                f'<p class="text-ssw-gray-600 text-sm">{esc(r.get("text"))}</p></div>'
            )

        body = (
            '<template x-if="open"><div class="question-card-body p-4">'
            + ('<h4 class="text-sm font-semibold text-ssw-charcoal mb-2">Numeric Responses</h4>'
               '<div class="response-list mb-4">' + "".join(num_items) + '</div>' if num_items else "")
            + ('<h4 class="text-sm font-semibold text-ssw-charcoal mb-2">Text Responses</h4>'
               '<div class="response-list">' + "".join(text_items) + '</div>' if text_items else "")
            + '</div></template>'
        )

        avg_label = f'{avg}/5' if avg is not None else '—'
        cards.append(
            f'<div x-data="{{ open: false }}" '
            '@expand-all.window="open = true" @collapse-all.window="open = false" '
            f'x-show="!searchQuery || \'{idx}\'.includes(searchQuery.toLowerCase())" '
            'class="bg-white rounded-lg border border-ssw-gray-200 overflow-hidden">'
            '<div class="question-card-header p-4 flex items-center justify-between" @click="open = !open">'
            '<div class="flex items-center gap-3 flex-1">'
            f'<div class="w-9 h-9 rounded-full bg-ssw-gray-100 flex items-center justify-center text-ssw-charcoal font-bold text-sm">{esc(initials(name))}</div>'
            '<div class="flex-1">'
            f'<p class="font-semibold text-ssw-charcoal">{esc(name)}</p>'
            '<div class="flex items-center gap-3 mt-1 flex-wrap">'
            f'<span class="text-xs text-ssw-gray-500">Avg: {esc(avg_label)}</span>'
            f'<span class="text-xs text-ssw-gray-500">{esc(rc)} responses</span>'
            f'{flag_html}</div></div>'
            f'<div class="score-bar max-w-[120px] flex-shrink-0"><div class="score-bar-fill {cls}" style="width: {pct:.0f}%"></div></div>'
            '</div>'
            '<span class="chevron-icon ml-3 text-ssw-gray-400" :class="open && \'open\'">▼</span>'
            '</div>' + body + '</div>'
        )
    return "".join(cards)


# ---------------------------------------------------------------------------
# Insights tab
# ---------------------------------------------------------------------------

_SEV = {"critical": "severity-critical", "high": "severity-high",
        "moderate": "severity-moderate", "low": "severity-low"}


def render_red_flags(flags):
    if not flags:
        return '<p class="text-ssw-charcoal">No signals worth flagging this week.</p>'
    out = []
    for f in flags:
        sev = (f.get("severity") or "moderate").lower()
        out.append(
            '<div class="bg-white rounded-lg p-4 mb-3 border border-ssw-gray-200">'
            '<div class="flex items-center justify-between gap-2 mb-1 flex-wrap">'
            f'<h3 class="font-semibold text-ssw-charcoal">{esc(f.get("flag"))}</h3>'
            f'<span class="{_SEV.get(sev, "severity-moderate")} text-xs px-2 py-0.5 rounded-full">{esc(sev)}</span>'
            '</div>'
            + (f'<p class="text-sm text-ssw-charcoal">{esc(f.get("evidence"))}</p>' if f.get("evidence") else "")
            + (f'<p class="text-sm text-ssw-gray-600 mt-1">→ {esc(f.get("prediction"))}</p>' if f.get("prediction") else "")
            + (f'<p class="text-xs text-ssw-gray-500 mt-1">When: {esc(f.get("timeToAct"))}</p>' if f.get("timeToAct") else "")
            + '</div>'
        )
    return "".join(out)


def render_adoption_gaps(gaps):
    if not gaps:
        return '<p class="text-ssw-gray-500">No significant adoption gaps — uptake is broad.</p>'
    out = ['<div class="space-y-3">']
    for g in gaps:
        out.append(
            '<div class="bg-amber-50 border-l-4 border-amber-400 rounded-r-lg p-4">'
            f'<h3 class="font-semibold text-ssw-charcoal">{esc(g.get("gap"))}</h3>'
            + (f'<p class="text-sm text-ssw-charcoal mt-1">{esc(g.get("evidence"))}</p>' if g.get("evidence") else "")
            + (f'<p class="text-sm text-ssw-gray-600 mt-1">Opportunity: {esc(g.get("opportunity"))}</p>' if g.get("opportunity") else "")
            + '</div>'
        )
    out.append('</div>')
    return "".join(out)


def render_recommendations(recs):
    tiers = [
        ("immediate", "➡️ Immediate (this week)"),
        ("shortTerm", "➡️ Short-term (this quarter)"),
        ("strategic", "➡️ Strategic (longer)"),
    ]
    blocks = []
    for key, label in tiers:
        items = (recs or {}).get(key) or []
        if not items:
            continue
        cards = []
        for r in items:
            meta = []
            if r.get("owner"):
                meta.append(f'<span><strong>Owner:</strong> {esc(r.get("owner"))}</span>')
            if r.get("rationale"):
                meta.append(f'<span class="md:col-span-2"><strong>Why:</strong> {esc(r.get("rationale"))}</span>')
            cards.append(
                '<div class="bg-white border border-ssw-gray-200 rounded-lg p-4">'
                f'<p class="font-medium text-ssw-charcoal">{esc(r.get("action"))}</p>'
                + ('<div class="grid grid-cols-1 md:grid-cols-3 gap-2 mt-2 text-xs text-ssw-gray-500">'
                   + "".join(meta) + '</div>' if meta else "")
                + (f'<p class="text-xs text-ssw-gray-500 mt-1"><strong>Success:</strong> {esc(r.get("successMetric"))}</p>'
                   if r.get("successMetric") else "")
                + '</div>'
            )
        blocks.append(
            '<div>'
            f'<h3 class="font-semibold text-ssw-charcoal mb-2">{label}</h3>'
            '<div class="space-y-2">' + "".join(cards) + '</div></div>'
        )
    if not blocks:
        return '<p class="text-ssw-gray-400">No recommendations generated.</p>'
    return '<div class="space-y-6">' + "".join(blocks) + '</div>'


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def render_chart_scripts(consolidated):
    ratings = [q for q in (consolidated.get("questionBreakdown") or [])
               if q.get("kind") == "rating" and q.get("mean") is not None]
    ratings.sort(key=lambda q: q.get("mean"))
    labels = [(q.get("text") or "")[:48] for q in ratings]
    means = [q.get("mean") for q in ratings]
    colors = ["#059669" if m >= 4 else "#F59E0B" if m >= 3 else "#CC4141" for m in means]

    so = consolidated.get("sentimentOverview") or {}
    breakdown = so.get("emotionalBreakdown") or {}
    stance_order = ["enthusiasm", "pragmatism", "curiosity", "skepticism", "frustration", "indifference"]
    radar_labels = [s.capitalize() for s in stance_order]
    radar_values = [breakdown.get(s, 0) or 0 for s in stance_order]

    return f"""
        const _scoreData = {{
            labels: {json.dumps(labels)},
            datasets: [{{
                label: 'Mean score',
                data: {json.dumps(means)},
                backgroundColor: {json.dumps(colors)},
                borderRadius: 4
            }}]
        }};
        const _sdEl = document.getElementById('scoreDistributionChart');
        if (_sdEl && _scoreData.labels.length) {{
            new Chart(_sdEl, {{
                type: 'bar',
                data: _scoreData,
                options: {{
                    indexAxis: 'y',
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{ x: {{ beginAtZero: true, max: 5 }} }},
                    responsive: true,
                    maintainAspectRatio: true
                }}
            }});
        }}

        const _radarEl = document.getElementById('emotionalRadarChart');
        if (_radarEl) {{
            new Chart(_radarEl, {{
                type: 'radar',
                data: {{
                    labels: {json.dumps(radar_labels)},
                    datasets: [{{
                        label: 'Stance %',
                        data: {json.dumps(radar_values)},
                        backgroundColor: 'rgba(204, 65, 65, 0.2)',
                        borderColor: '#CC4141',
                        pointBackgroundColor: '#CC4141'
                    }}]
                }},
                options: {{
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{ r: {{ beginAtZero: true, suggestedMax: {max(radar_values) + 10 if radar_values else 50} }} }}
                }}
            }});
        }}
    """


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 4:
        sys.stderr.write("usage: build-dashboard.py <consolidated.json> <template.html> <out.html>\n")
        sys.exit(2)
    consolidated_path, template_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(consolidated_path, "r", encoding="utf-8") as f:
        c = json.load(f)
    with open(template_path, "r", encoding="utf-8") as f:
        tpl = f.read()

    meta = c.get("metadata") or {}
    exec_sum = c.get("executiveSummary") or {}

    replacements = {
        "{{SURVEY_NAME}}": esc(meta.get("surveyName") or meta.get("topic") or "Survey"),
        "{{DATE}}": esc(meta.get("dateRange") or ""),
        "{{RESPONSE_COUNT}}": esc(meta.get("responseCount") or 0),
        "{{COMPLETION_RATE}}": esc(meta.get("completionRate") or 100),
        "{{PER_SURVEY_COUNTS}}": "",
        "{{SURVEY_GROUP_HEADER}}": "",
        "{{KEY_METRICS_CARDS}}": render_key_metrics(c.get("keyMetrics")),
        "{{EXECUTIVE_SUMMARY}}": render_exec_summary(exec_sum.get("bullets")),
        "{{OVERALL_VERDICT}}": esc(exec_sum.get("overallVerdict")),
        "{{OVERALL_GRADE}}": esc(c.get("overallGrade") or ""),
        "{{FOCUS_SUMMARY}}": render_focus_summary(c.get("focusSummary")),
        "{{STANDOUT_RESPONSES}}": render_standouts(c.get("standoutResponses")),
        "{{HARD_TRUTHS}}": render_hard_truths(c.get("hardTruths")),
        "{{QUESTION_BREAKDOWN}}": render_question_breakdown(c),
        "{{SENTIMENT_OVERVIEW}}": render_sentiment_overview(c.get("sentimentOverview")),
        "{{THEME_CARDS}}": render_theme_cards(c.get("themes")),
        "{{NOTABLE_QUOTES}}": render_notable_quotes(c.get("notableQuotes")),
        "{{PEOPLE_CARDS}}": render_people_cards(c.get("people")),
        "{{RED_FLAGS}}": render_red_flags(c.get("redFlags")),
        "{{RISK_RADAR}}": render_adoption_gaps(c.get("adoptionGaps")),
        "{{RECOMMENDATIONS}}": render_recommendations(c.get("recommendations")),
        "{{CHART_SCRIPTS}}": render_chart_scripts(c),
        "{{GENERATED_AT}}": esc(f"Generated from {meta.get('responseCount', 0)} responses"),
    }

    for ph, val in replacements.items():
        tpl = tpl.replace(ph, val if isinstance(val, str) else str(val))

    # scrub any placeholder we did not explicitly fill
    tpl = re.sub(r"\{\{[A-Z_]+\}\}", "", tpl)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(tpl)

    qn = len(c.get("questionBreakdown") or [])
    ft = len(c.get("freeTextQuestions") or [])
    pe = len((c.get("people") or {}).get("respondents") or [])
    print(f"[build-dashboard] wrote {out_path} ({qn} questions, {ft} free-text, {pe} people)")


if __name__ == "__main__":
    main()
