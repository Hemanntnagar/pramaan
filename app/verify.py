"""
verify.py — the actual audit-verification logic.

This is a direct port of the rules used in the earlier browser-only demo,
now living server-side so there's exactly one place this logic is defined
(the browser version duplicated this in JS, which is fine for a throwaway
demo but is the kind of thing that quietly drifts out of sync in a real
product — this backend is the fix for that).
"""

from datetime import datetime

SEVERITY_WEIGHT = {"low": 1, "medium": 2, "high": 4}


def score_to_verdict(score: int):
    if score == 0:
        return "Verified — no issues found", "verified"
    if score <= 3:
        return "Flagged — low risk", "low"
    if score <= 7:
        return "Flagged — medium risk", "medium"
    return "Flagged — high risk", "high"


def run_verification(payload: dict, conn, db) -> dict:
    """
    payload shape:
    {
        "name": str, "period": "YYYY-MM", "claimed": float, "capacity": float,
        "rate_min": float, "rate_max": float,
        "docs": [{"invoice": str, "date": "YYYY-MM-DD", "qty": float, "rate": float}, ...]
    }
    """
    name = (payload.get("name") or "Unnamed facility").strip() or "Unnamed facility"
    period = payload.get("period") or ""
    claimed = float(payload.get("claimed") or 0)
    capacity = float(payload.get("capacity") or 0)
    rate_min = float(payload.get("rate_min") or 0)
    rate_max = float(payload.get("rate_max") or float("inf"))
    docs = [
        {
            "invoice": (d.get("invoice") or "").strip(),
            "date": d.get("date") or "",
            "qty": float(d.get("qty") or 0),
            "rate": float(d.get("rate") or 0),
        }
        for d in (payload.get("docs") or [])
        if (d.get("invoice") or d.get("qty"))
    ]

    flags = []
    doc_sum = sum(d["qty"] for d in docs)

    # Rule 1 — claimed vs. documented volume
    if docs and claimed > 0:
        diff_pct = abs(doc_sum - claimed) / claimed * 100
        if diff_pct > 25:
            flags.append({"severity": "high", "text": (
                f"Claimed quantity ({claimed:g} kg) is {diff_pct:.0f}% off from what the supporting "
                f"documents add up to ({doc_sum:.0f} kg). A gap this large needs a direct explanation "
                f"from the producer before this case can clear."
            )})
        elif diff_pct > 10:
            flags.append({"severity": "medium", "text": (
                f"Claimed quantity ({claimed:g} kg) does not quite match the documents ({doc_sum:.0f} kg) "
                f"— a {diff_pct:.0f}% gap. Worth a closer look."
            )})

    # Rule 2 — no documents at all
    if not docs and claimed > 0:
        flags.append({"severity": "high", "text": (
            f"No supporting documents were provided for a claimed {claimed:g} kg. A claim with no paper "
            f"trail behind it is the single biggest red flag in this audit."
        )})

    # Rule 3 — capacity breach / near-capacity
    if capacity > 0 and claimed > capacity:
        flags.append({"severity": "high", "text": (
            f"Claimed volume ({claimed:g} kg) exceeds the facility's registered monthly capacity "
            f"({capacity:g} kg). This is physically implausible unless the capacity registration "
            f"itself is outdated."
        )})
    elif capacity > 0 and claimed > capacity * 0.95:
        flags.append({"severity": "low", "text": (
            f"Claimed volume is right at the edge of registered capacity "
            f"({(claimed/capacity)*100:.0f}% utilised). Not necessarily wrong, but worth confirming "
            f"the capacity figure is current."
        )})

    # Rule 4 — document dated outside the reporting period
    if period:
        for d in docs:
            if d["date"] and d["date"][:7] != period:
                flags.append({"severity": "medium", "text": (
                    f"Document {d['invoice'] or '(no number)'} is dated {d['date']}, which falls "
                    f"outside the {period} reporting period — check whether volume is being shifted "
                    f"across periods."
                )})

    # Rule 5 — duplicate invoice number within this same submission
    seen = {}
    for d in docs:
        if d["invoice"]:
            seen[d["invoice"]] = seen.get(d["invoice"], 0) + 1
    for inv, count in seen.items():
        if count > 1:
            flags.append({"severity": "high", "text": (
                f'Invoice / e-way bill number "{inv}" appears {count} times in this submission. '
                f"A repeated invoice number is a classic sign of the same material being counted "
                f"more than once."
            )})

    # Rule 6 — duplicate invoice number across *every other case ever saved*
    # This is the check a single-case-only tool structurally cannot do.
    for d in docs:
        if not d["invoice"]:
            continue
        match = db.find_invoice_elsewhere(conn, d["invoice"])
        if match:
            flags.append({"severity": "high", "text": (
                f'Invoice / e-way bill number "{d["invoice"]}" was already used in a different case '
                f'file ({match["case_no"]}, {match["name"]}). The same document showing up in two '
                f"separate audits is a strong sign of reuse or double-counting across producers."
            )})

    # Rule 7 — rate per kg outside the typical range
    for d in docs:
        if d["rate"] > 0 and (d["rate"] < rate_min or d["rate"] > rate_max):
            flags.append({"severity": "medium", "text": (
                f"Document {d['invoice'] or '(no number)'} is priced at ₹{d['rate']:g}/kg, outside "
                f"the typical ₹{rate_min:g}–₹{rate_max:g}/kg range entered for this material — worth "
                f"confirming the pricing is genuine."
            )})

    score = sum(SEVERITY_WEIGHT[f["severity"]] for f in flags)
    verdict, verdict_class = score_to_verdict(score)
    case_no = db.next_case_no(conn)

    record = {
        "case_no": case_no,
        "name": name,
        "period": period,
        "claimed": claimed,
        "capacity": capacity,
        "doc_sum": doc_sum,
        "docs": docs,
        "flags": flags,
        "score": score,
        "verdict": verdict,
        "verdict_class": verdict_class,
        "ran_at": datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p"),
    }
    return record
