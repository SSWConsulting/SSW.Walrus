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

import base64
import html
import json
import os
import re
import sys


def logo_data_uri(name="ssw-logo.png"):
    """Inline the official SSW logo as a base64 data URI (self-contained HTML)."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name)
    try:
        with open(p, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""


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


def avatar_html(name, photo_url, px=36):
    """Round SSW-profile-photo avatar with an initials fallback.

    When photo_url is set, render an <img> tagged .js-avatar; the template's
    onerror handler swaps it for the initials placeholder if the photo 404s
    (non-SSW or unresolved names arrive with photo_url=None and skip the <img>
    entirely, so we never point at the wrong person). Mirrors SSW.Tiger.
    """
    ini = esc(initials(name))
    box = f'width:{px}px;height:{px}px'
    if photo_url:
        return (
            f'<div class="avatar" style="{box}">'
            f'<img class="avatar-img js-avatar" data-initials="{ini}" loading="lazy" '
            f'src="{esc(photo_url)}" alt="{esc(name)}"></div>'
        )
    return f'<div class="avatar avatar-fallback" style="{box}">{ini}</div>'


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
        '<h2 class="text-lg text-ssw-charcoal mb-2 font-bold">Focus Area</h2>'
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
        '<h2 class="text-lg text-ssw-charcoal mb-4">Standout Responses</h2>'
        + "".join(cards) + '</section>'
    )


def render_recap_video(out_html_path, video_name="walkthrough.mp4"):
    """Embed a recap player on Overview iff the walkthrough was rendered next to index.html."""
    d = os.path.dirname(os.path.abspath(out_html_path))
    if not os.path.exists(os.path.join(d, video_name)):
        return ""
    poster = video_name.rsplit(".", 1)[0] + "-poster.jpg"
    poster_attr = f' poster="{poster}"' if os.path.exists(os.path.join(d, poster)) else ""
    return (
        '<section class="bg-white rounded-xl shadow-sm ssw-card p-4 mb-6">'
        '<h2 class="text-lg text-ssw-charcoal mb-3 flex items-center">'
        '<span class="w-3 h-3 bg-ssw-red rounded-full mr-2"></span>This week\'s recap</h2>'
        f'<video controls preload="none"{poster_attr} class="w-full rounded-lg" style="max-height:540px;background:#1a1a1a">'
        f'<source src="{video_name}" type="video/mp4">'
        f'Your browser can\'t play this video — <a href="{video_name}" class="text-ssw-red underline">download the recap</a>.'
        '</video>'
        '<p class="text-xs text-ssw-gray-400 mt-2">A ~3-minute narrated recap of this week\'s responses.</p>'
        '</section>'
    )


def render_hard_truths(truths):
    # No hard truths -> no section. A box announcing it has nothing to say is
    # worse than absence, and forcing the section invites manufactured drama.
    if not truths:
        return ""
    items = "".join(
        '<div class="flex items-start">'
        f'<p class="text-ssw-charcoal">{esc(t)}</p></div>'
        for t in truths
    )
    return (
        '<section class="mb-6 bg-ssw-red-50 border-l-4 border-ssw-red rounded-r-ds p-6">'
        '<h2 class="text-lg text-ssw-red-700 mb-4 flex items-center font-bold">Hard Truths</h2>'
        f'<div class="space-y-2 text-ssw-charcoal">{items}</div>'
        '</section>'
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
    """Free-text card: lead with the AI-curated insightful/opinionated picks;
    keep every raw response behind a 'Show all' toggle."""
    text = q.get("text", "")
    responses = q.get("responses") or q.get("individualResponses") or []
    curated = q.get("curated") or []
    rc = q.get("responseCount", len(responses))
    idx = sidx(text, "free text", *[r.get("respondent", "") for r in responses[:10]])

    if curated:
        curated_html = (
            '<p class="text-xs font-semibold uppercase tracking-wide text-ssw-gray-500 mb-2">'
            'Most insightful responses</p>'
            '<div class="response-list">' + "".join(_text_response_item(r) for r in curated) + '</div>'
        )
        show_all = (
            f'<button class="show-more-btn" @click="showAll = !showAll" '
            f'x-text="showAll ? \'Hide all responses\' : \'Show all {len(responses)} responses\'"></button>'
            '<div x-show="showAll" x-cloak class="response-list mt-2">'
            + "".join(_text_response_item(r) for r in responses) + '</div>'
        )
        inner = curated_html + show_all
    else:
        # nothing substantive to curate — just show them all
        inner = '<div class="response-list">' + paginated_responses(responses, _text_response_item) + '</div>'

    body = '<template x-if="open"><div class="question-card-body p-4">' + inner + '</div></template>'

    badge = (f'<span class="text-xs text-ssw-gray-500">{len(curated)} picks · {esc(rc)} responses</span>'
             if curated else f'<span class="text-xs text-ssw-gray-500">{esc(rc)} responses</span>')
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
        f'{badge}'
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


def render_notable_quotes_section(quotes):
    """Full Notable Quotes section, or "" when there are none (section omitted)."""
    quotes = quotes or []
    if not quotes:
        return ""
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
    return (
        '<section class="mt-6 bg-white rounded-xl shadow-sm ssw-card p-6">'
        '<h2 class="text-lg text-ssw-charcoal mb-4">Notable Quotes</h2>'
        '<div class="space-y-4">' + "".join(out) + '</div></section>'
    )


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
            f'{avatar_html(name, p.get("photoUrl"), 36)}'
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
        ("immediate", "Immediate (this week)"),
        ("shortTerm", "Short-term (this quarter)"),
        ("strategic", "Strategic (longer)"),
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
# Blockers tab — the standing "was anyone blocking you?" question
# ---------------------------------------------------------------------------
# Owned exclusively by this tab: who is blocked, who by, and what the block is.
# The whole tab (and its nav item) disappears when the survey has no such
# question, which is every survey that is not a CTF form.

_BLOCKER_TONE = {
    "high": ("bg-ssw-red-50", "border-ssw-red", "severity-critical"),
    "moderate": ("bg-amber-50", "border-amber-400", "severity-high"),
    "low": ("bg-white", "border-ssw-gray-300", "severity-moderate"),
    None: ("bg-white", "border-ssw-gray-300", "severity-moderate"),
}

_BLOCKERS_NAV = (
    '<button @click="activeTab = \'blockers\'" '
    ':class="activeTab === \'blockers\' ? \'ds-navitem ds-navitem--active\' : \'ds-navitem\'">'
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
    '<circle cx="12" cy="12" r="10"/><line x1="4.9" y1="4.9" x2="19.1" y2="19.1"/></svg>'
    '<span>Blockers</span></button>'
)


def render_blockers_nav(b):
    return _BLOCKERS_NAV if b else ""


def render_tab_list(b):
    """The mobile tab row's Alpine array literal — Blockers only when present."""
    tabs = [("overview", "Overview"), ("responses", "Responses"), ("themes", "Themes"),
            ("people", "People")]
    if b:
        tabs.append(("blockers", "Blockers"))
    tabs.append(("insights", "Insights"))
    return "[" + ",".join(f"['{k}','{label}']" for k, label in tabs) + "]"


def _blocker_stat(label, value, context, tone="text-ssw-charcoal"):
    return (
        '<div class="bg-white rounded-xl shadow-sm ssw-card p-4">'
        f'<p class="text-xs text-ssw-gray-500 font-semibold uppercase tracking-wide">{esc(label)}</p>'
        f'<p class="text-2xl font-bold {tone} mt-1">{esc(value)}</p>'
        f'<p class="text-xs text-ssw-gray-400 mt-1">{esc(context)}</p>'
        '</div>'
    )


def _blocker_person_card(p):
    bg, border, badge = _BLOCKER_TONE.get(p.get("severity"), _BLOCKER_TONE[None])
    label = p.get("severityLabel")
    badge_html = (f'<span class="{badge} text-xs px-2 py-0.5 rounded-full">{esc(label)}</span>'
                  if label else "")
    detail = p.get("detail")
    body = (f'<blockquote class="quote-block">&ldquo;{esc(detail)}&rdquo;</blockquote>'
            if detail else
            '<p class="text-sm text-ssw-gray-500">No detail given — worth asking them.</p>')
    return (
        f'<div class="{bg} border-l-4 {border} rounded-r-lg p-4">'
        '<div class="flex items-center gap-3 mb-2 flex-wrap">'
        + avatar_html(p.get("respondent"), p.get("photoUrl"), px=32)
        + f'<span class="font-semibold text-ssw-charcoal">{esc(p.get("respondent"))}</span>'
        + badge_html
        + '<span class="text-xs text-ssw-gray-500 ml-auto">Blocked by '
        f'<strong class="text-ssw-charcoal">{esc(p.get("blockedBy"))}</strong></span>'
        '</div>' + body + '</div>'
    )


def render_blockers_tab(b):
    if not b:
        return ""
    people = b.get("people") or []
    blocked = b.get("blockedCount") or 0
    total = b.get("responseCount") or 0
    high = (b.get("severityCounts") or {}).get("high") or 0
    owner = b.get("blockedBy") or "the person who asked"

    tiles = "".join([
        _blocker_stat("Blocked this week", blocked, f"of {total} who answered",
                      "text-ssw-red" if blocked else "text-green-600"),
        _blocker_stat(f"Blocked by {owner}", b.get("byOwner") or 0,
                      "the standing question's own option"),
        _blocker_stat("Blocked by someone else", b.get("bySomeoneElse") or 0,
                      "a colleague, not " + owner),
        _blocker_stat("More than a day", high, "the most severe option on the form",
                      "text-ssw-red" if high else "text-ssw-charcoal"),
    ])

    if people:
        cards = '<div class="space-y-3">' + "".join(_blocker_person_card(p) for p in people) + '</div>'
    else:
        cards = ('<div class="bg-green-50 border-l-4 border-green-600 rounded-r-lg p-4">'
                 '<p class="text-ssw-charcoal">Nobody reported being blocked this week.</p></div>')

    review = ""
    if b.get("needsReview"):
        items = "".join(
            '<div class="bg-white rounded-lg p-3 mb-2 border border-ssw-gray-200">'
            f'<p class="font-semibold text-ssw-charcoal text-sm">{esc(r.get("respondent"))}</p>'
            f'<p class="text-sm text-ssw-charcoal">{esc(r.get("answer"))}</p>'
            + (f'<p class="text-sm text-ssw-gray-600 mt-1">{esc(r.get("detail"))}</p>'
               if r.get("detail") else "")
            + '</div>'
            for r in b["needsReview"]
        )
        review = (
            '<section class="mb-6 bg-amber-50 border-l-4 border-amber-400 rounded-r-ds p-6">'
            '<h2 class="text-lg text-ssw-charcoal mb-2 font-bold">Typed their own answer — read these</h2>'
            '<p class="text-sm text-ssw-charcoal mb-4">Not counted above. These went in the '
            '&ldquo;Other&rdquo; box, and the prose often contradicts the word it opens with, '
            'so a person decides what they mean.</p>'
            + items + '</section>'
        )

    question = b.get("question") or ""
    detail_q = b.get("detailQuestion") or ""
    footnote = (
        '<p class="text-xs text-ssw-gray-400 mt-6">Asked as: &ldquo;'
        + esc(question) + '&rdquo;'
        + (' &middot; follow-up: &ldquo;' + esc(detail_q) + '&rdquo;' if detail_q else "")
        + '</p>'
    )

    return (
        '<div x-show="activeTab === \'blockers\'" x-cloak>'
        f'<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">{tiles}</div>'
        '<section class="bg-white rounded-xl shadow-sm ssw-card p-6 mb-6">'
        '<h2 class="text-lg text-ssw-charcoal mb-2 flex items-center">'
        '<span class="w-3 h-3 bg-ssw-red rounded-full mr-2"></span>'
        'Who is blocked, and what by</h2>'
        '<p class="text-sm text-ssw-gray-500 mb-6">Self-reported. The form defines blocked as '
        'having tried about twice over two days, leaving a message each time.</p>'
        + cards + footnote + '</section>' + review + '</div>'
    )


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
        const _radarData = {json.dumps(radar_values)};
        if (_radarEl && _radarData.some(v => v > 0)) {{
            new Chart(_radarEl, {{
                type: 'radar',
                data: {{
                    labels: {json.dumps(radar_labels)},
                    datasets: [{{
                        label: 'Stance %',
                        data: _radarData,
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
        }} else if (_radarEl) {{
            const _sec = _radarEl.closest('section');
            if (_sec) _sec.style.display = 'none';
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
        "{{SSW_LOGO}}": logo_data_uri(),
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
        "{{RECAP_VIDEO}}": render_recap_video(out_path),
        "{{FOCUS_SUMMARY}}": render_focus_summary(c.get("focusSummary")),
        "{{STANDOUT_RESPONSES}}": render_standouts(c.get("standoutResponses")),
        "{{HARD_TRUTHS_SECTION}}": render_hard_truths(c.get("hardTruths")),
        "{{QUESTION_BREAKDOWN}}": render_question_breakdown(c),
        "{{SENTIMENT_OVERVIEW}}": render_sentiment_overview(c.get("sentimentOverview")),
        "{{THEME_CARDS}}": render_theme_cards(c.get("themes")),
        "{{PEOPLE_CARDS}}": render_people_cards(c.get("people")),
        "{{BLOCKERS_NAV}}": render_blockers_nav(c.get("blockers")),
        "{{TAB_LIST}}": render_tab_list(c.get("blockers")),
        "{{BLOCKERS_TAB}}": render_blockers_tab(c.get("blockers")),
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
    bl = c.get("blockers")
    blocked = f", {bl['blockedCount']} blocked" if bl else ""
    print(f"[build-dashboard] wrote {out_path} ({qn} questions, {ft} free-text, {pe} people{blocked})")


if __name__ == "__main__":
    main()
