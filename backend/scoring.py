"""All investment rules live here (ported from the original single-file app)."""
import math

FIELDS = ["ca", "cl", "debt", "eq", "cash", "rev", "ni"]
HORIZONS = {
    "short": "short term (up to 1 year)",
    "medium": "medium term (1–3 years)",
    "long": "long term (3+ years)",
}


def band(s):
    return "G" if s >= 70 else "Y" if s >= 45 else "R"


def score_company(c):
    """Layer 1: balance-sheet safety score out of 100."""
    cr = c["ca"] / c["cl"] if c["cl"] > 0 else 9
    de = c["debt"] / c["eq"] if c["eq"] > 0 else 99
    nm = c["ni"] / c["rev"] if c["rev"] > 0 else -1
    cd = c["cash"] / c["debt"] if c["debt"] > 0 else 9

    a = 25 if cr >= 2 else 20 if cr >= 1.5 else 12 if cr >= 1 else 3
    b = 25 if de <= .5 else 20 if de <= 1 else 10 if de <= 2 else 2
    m = 25 if nm >= .15 else 20 if nm >= .08 else 10 if nm >= 0 else 0
    d = 25 if cd >= .5 else 15 if cd >= .25 else 8 if cd >= .1 else 2
    return {"s": a + b + m + d, "cr": cr, "de": de, "nm": nm, "cd": cd}


def analyze(companies, budget, risk):
    """Score every company and split the budget across the ones that pass (score >= 45)."""
    results = [{**c, **score_company(c)} for c in companies]
    ok = [c for c in results if c["s"] >= 45]
    total = sum(math.pow(c["s"], risk) for c in ok)
    for c in results:
        c["pct"] = math.pow(c["s"], risk) / total if c["s"] >= 45 and total else 0
        c["amount"] = budget * c["pct"]
        c["band"] = band(c["s"])
    results.sort(key=lambda c: c["s"], reverse=True)
    return results


def _mean(a):
    return sum(a) / len(a)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def price_signal(safety_score, prices):
    """Layer 2: price-trend timing blended with balance-sheet safety."""
    P = prices
    n = len(P)
    k = max(3, n // 3)
    sh = _mean(P[-k:])
    lg = _mean(P)
    ch = (P[-1] / P[0] - 1) * 100
    r = [P[i + 1] / P[i] - 1 for i in range(n - 1)]
    m = _mean(r)
    vol = math.sqrt(_mean([(x - m) ** 2 for x in r])) * 100

    tm = clamp(50 + clamp(ch * 2, -25, 25) + (10 if sh > lg else -10) - clamp(vol * 5, 0, 25), 0, 100)
    final = int(math.floor(.6 * safety_score + .4 * tm + .5))
    sig = band(final)
    if safety_score < 45:
        sig = "R"
    messages = {
        "G": "Good moment to buy: strong company and a healthy trend.",
        "Y": "Be careful: wait for a clearer trend or buy in small parts.",
        "R": "Not safe to buy now.",
    }
    return {
        "signal": sig,
        "message": messages[sig],
        "timing_score": tm,
        "final_score": final,
        "safety_score": safety_score,
        "change_pct": ch,
        "volatility_pct": vol,
        "rising": sh > lg and ch > 0,
        "recent_above_avg": sh > lg,
        "prices": P,
    }


def _verdict(s):
    if s >= 70:
        return "The fundamentals are relatively strong."
    if s >= 45:
        return "The fundamentals are mixed, so caution is appropriate."
    return "The fundamentals are weak under the current scoring rules."


def _period_text(h):
    return {
        "short": "For a short horizon, price momentum, volatility and downside risk matter more because there is less time to recover from a poor entry.",
        "medium": "For a medium horizon, both business quality and a reasonable entry price matter. A balanced approach is more appropriate.",
        "long": "For a long horizon, business quality, debt control, profitability and durable fundamentals matter more than short-term price noise.",
    }[h]


def _de_text(c):
    return f"{c['de']:.2f}" if c["eq"] > 0 else "n/a"


def assistant_summary(c, horizon, timing_score=None):
    s = c["s"]
    outlook = ("stronger fundamental position" if s >= 70
               else "moderate fundamental position" if s >= 45
               else "weak fundamental position")
    return {
        "name": c["name"],
        "horizon_label": HORIZONS[horizon],
        "outlook": outlook,
        "safety": s,
        "current_ratio": round(c["cr"], 2),
        "debt_to_equity": _de_text(c),
        "net_margin_pct": round(c["nm"] * 100, 1),
        "price_trend_score": None if timing_score is None else round(timing_score),
    }


def assistant_answer(c, horizon, question):
    """Rule-based educational answer (same rules as the original assistant)."""
    ql = question.lower()
    verdict = _verdict(c["s"])
    period = _period_text(horizon)
    name = c["name"]

    if "risk" in ql:
        return (f"{name}: {verdict} Main risks to watch are leverage (debt-to-equity {_de_text(c)}), "
                f"liquidity (current ratio {c['cr']:.2f}), profitability (net margin {c['nm']*100:.1f}%), "
                f"and price volatility. {period}")
    if "buy" in ql or "wait" in ql:
        return (f"{name}: {verdict} {period} The assistant would not treat this as a blind buy signal; "
                "use the Buy Signal layer together with the fundamental score and consider waiting when the price trend is weak.")
    if "suitable" in ql or "good for" in ql or "time period" in ql:
        return (f"{name}: {verdict} {period} Current safety score is {c['s']}/100. "
                "This indicates how well the company fits the framework, not a guaranteed return.")
    if "explain" in ql or "simple" in ql:
        return (f"{name} has a safety score of {c['s']}/100. Its current ratio is {c['cr']:.2f}, "
                f"debt-to-equity is {_de_text(c)}, and net margin is {c['nm']*100:.1f}%. {period}")
    return (f"{name}: {verdict} You selected {HORIZONS[horizon]}. {period} "
            "You can ask me about suitability, risks, or whether to buy/wait.")
