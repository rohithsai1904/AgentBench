from statistics import mean

LABELS = ("good", "bad")


"""
labeled = [(case, output, "good" or "bad"), ...]     # 10 of them, labeled by you
report = asyncio.run(calibrate(ExactMatch(), labeled))
"""

async def calibrate(evaluator, labeled_cases, *, show=True) -> dict:
    rows = []
    for i, (case, output, label) in enumerate(labeled_cases):
        if label not in LABELS:
            raise ValueError(f"row {i}: label must be 'good' or 'bad', got {label!r}")
        try:
            score = await evaluator.score(case, output)
        except Exception as exc:                    # one broken row must not hide the rest
            rows.append({"case_id": getattr(case, "id", str(i)), "label": label, "value": None,
                         "passed": None, "agrees": None, "note": f"error: {type(exc).__name__}: {exc}"})
            continue
        agrees = None if score.value is None else (score.passed == (label == "good"))
        rows.append({"case_id": getattr(case, "id", str(i)), "label": label, "value": score.value,
                     "passed": score.passed, "agrees": agrees, "note": score.reason})

    scored = [r for r in rows if r["value"] is not None]
    good = [r["value"] for r in scored if r["label"] == "good"]
    bad = [r["value"] for r in scored if r["label"] == "bad"]
    judged = [r for r in rows if r["agrees"] is not None]
    report = {
        "evaluator": evaluator.name,
        "threshold": evaluator.threshold,
        "rows": rows,
        "good_mean": mean(good) if good else None,
        "bad_mean": mean(bad) if bad else None,
        "gap": (mean(good) - mean(bad)) if good and bad else None,      # want this clearly positive
        "agreement": (sum(r["agrees"] for r in judged) / len(judged)) if judged else None,
        "not_scored": len(rows) - len(scored),
        "disagreements": [r["case_id"] for r in judged if not r["agrees"]],
    }
    if show:
        print(report)
    return report
