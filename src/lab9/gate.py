"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems = _report_problems(pr, spec, "")
    problems += _report_problems(base, spec, "baseline: ")
    problems += _compare_problems(pr, base)
    if base_spec is not None:
        problems += _ratchet_problems(spec, base_spec)
    return problems


def _is_bad_number(v) -> bool:
    return isinstance(v, float) and not math.isfinite(v)


def _graded_ids(spec: dict) -> list[str]:
    """Metric ids (spec metrics and slice metrics) that a grader must have scored on every row."""
    ids = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    ids += [sl["metric"] for sl in spec.get("slices") or [] if sl.get("metric") in GRADERS]
    return list(dict.fromkeys(ids))


def _report_problems(rep: dict, spec: dict, who: str) -> list[str]:
    """Checks that need only one report: finite numbers, row count, duplicates, crashed graders,
    and headline metrics that really are the aggregate of the rows."""
    out: list[str] = []
    rows = rep.get("rows")
    if not isinstance(rows, list) or not rows:
        return [f"{who}report has no rows"]
    for k, v in (rep.get("metrics") or {}).items():
        if _is_bad_number(v):
            out.append(f"{who}metric {k} is {v} (not finite)")
    bad_cells = sorted({k for r in rows for k, v in r.items() if _is_bad_number(v)})
    if bad_cells:
        out.append(f"{who}rows hold NaN/inf values in: {', '.join(bad_cells)}")
    man = rep.get("manifest") or {}
    seeds = man.get("seeds") or []
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dupes = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dupes:
        out.append(f"{who}{len(dupes)} duplicated (item_id, seed) row(s), e.g. {dupes[0]}")
    if len(set(seeds)) != len(seeds):
        out.append(f"{who}manifest lists duplicate seeds {seeds}")
    want = (man.get("items") or 0) * len(seeds)
    if len(rows) != want:
        out.append(f"{who}{len(rows)} rows but manifest says {man.get('items')} items x {len(seeds)} seeds = {want}")
    n_items = len({r.get("item_id") for r in rows})
    if n_items != man.get("items"):
        out.append(f"{who}{n_items} distinct items in rows but manifest says {man.get('items')}")
    off = sorted({r.get("seed") for r in rows} - set(seeds), key=str)
    if off:
        out.append(f"{who}rows use seeds {off} not listed in manifest seeds {seeds}")
    if "evaluator_failures" not in rep:
        out.append(f"{who}report has no evaluator_failures field")
    elif rep["evaluator_failures"]:
        out.append(f"{who}{len(rep['evaluator_failures'])} evaluator failure(s), first: {rep['evaluator_failures'][0]}")
    for m in _graded_ids(spec):
        missing = sum(1 for r in rows if r.get(m) is None)
        if missing:
            out.append(f"{who}{missing} row(s) have no value for graded metric {m} (grader crashed or row edited)")
    # Headline numbers must be the aggregate of the rows: editing "metrics" by hand games every threshold.
    for m in _graded_ids(spec):
        vals = [float(r[m]) for r in rows if r.get(m) is not None and not _is_bad_number(r[m])]
        got = (rep.get("metrics") or {}).get(m)
        if not vals or got is None or _is_bad_number(got):
            continue
        agg = sum(vals) if m in ("secret_leak", "approval_bypass") else sum(vals) / len(vals)
        if abs(float(got) - agg) > 0.002:
            out.append(f"{who}metric {m} = {got} but the rows aggregate to {agg:.4f}")
    # pass@k / pass^k are derived from the pass_rate rows the same way eval.aggregate does.
    by_item: dict = {}
    for r in rows:
        by_item.setdefault(r.get("item_id"), []).append(bool(r.get("pass_rate")))
    for name, fn in (("pass_at", stats.pass_at_k), ("pass_hat", stats.pass_hat_k)):
        for key, got in (rep.get("metrics") or {}).items():
            if not (key.startswith(name + "_") and key[len(name) + 1:].isdigit()) or got is None or _is_bad_number(got):
                continue
            k = int(key[len(name) + 1:])
            if not by_item or min(len(v) for v in by_item.values()) < k:
                continue
            agg = sum(fn(len(v), sum(v), k) for v in by_item.values()) / len(by_item)
            if abs(float(got) - agg) > 0.002:
                out.append(f"{who}metric {key} = {got} but the rows aggregate to {agg:.4f}")
    # An item carries one fixed set of slice tags in every seed of one report.
    tags: dict = {}
    for r in rows:
        tags.setdefault(r.get("item_id"), set()).add(frozenset(r.get("slices") or []))
    odd = sorted(str(i) for i, t in tags.items() if len(t) > 1)
    if odd:
        out.append(f"{who}slice tags differ between seeds of the same item: {', '.join(odd)}")
    return out


def _compare_problems(pr: dict, base: dict) -> list[str]:
    out: list[str] = []
    a = {(r.get("item_id"), r.get("seed")) for r in pr.get("rows") or []}
    b = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if a != b:
        miss, extra = sorted(b - a, key=str), sorted(a - b, key=str)
        out.append(f"(item, seed) set differs from the baseline: {len(miss)} missing {miss[:3]}, "
                   f"{len(extra)} extra {extra[:3]}")
    tags_pr = {r.get("item_id"): frozenset(r.get("slices") or []) for r in pr.get("rows") or []}
    tags_b = {r.get("item_id"): frozenset(r.get("slices") or []) for r in base.get("rows") or []}
    moved = sorted(str(i) for i in tags_pr.keys() & tags_b.keys() if tags_pr[i] != tags_b[i])
    if moved:
        out.append(f"slice tags changed versus the baseline for: {', '.join(moved)}")
    return out


def _loose_threshold(new: dict, old: dict) -> list[str]:
    """What in `new` is looser than `old`. A key that disappeared counts as loosened."""
    out = []
    for key, tighter in (("max", lambda n, o: n <= o), ("min", lambda n, o: n >= o),
                         ("max_increase", lambda n, o: n <= o)):
        if key in old and (key not in new or not tighter(float(new[key]), float(old[key]))):
            out.append(f"{key} {old[key]} -> {new.get(key, 'removed')}")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        out.append("no_significant_drop removed")
    return out


def _ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    """Thresholds may only get stricter within one eval-set version (a new version = new baseline)."""
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []
    out: list[str] = []
    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for old in base_spec.get("metrics", []):
        new = new_m.get(old["id"])
        if new is None:
            out.append(f"ratchet: metric {old['id']} removed from the spec")
            continue
        for why in _loose_threshold(new.get("threshold") or {}, old.get("threshold") or {}):
            out.append(f"ratchet: metric {old['id']} loosened ({why})")
        if old.get("blocking") and not new.get("blocking"):
            out.append(f"ratchet: metric {old['id']} is no longer blocking")
        if old.get("kind") == "safety" and new.get("kind") != "safety":
            out.append(f"ratchet: metric {old['id']} is no longer a safety metric")
    new_s = {sl["name"]: sl for sl in spec.get("slices") or []}
    for old in base_spec.get("slices") or []:
        new = new_s.get(old["name"])
        if new is None:
            out.append(f"ratchet: slice {old['name']} removed from the spec")
            continue
        if new.get("metric") != old.get("metric"):
            out.append(f"ratchet: slice {old['name']} now measures {new.get('metric')} instead of {old.get('metric')}")
        keep = {k: v for k, v in old.items() if k in ("min", "no_significant_drop")}
        for why in _loose_threshold(new, keep):
            out.append(f"ratchet: slice {old['name']} loosened ({why})")
        if old.get("blocking", True) and not new.get("blocking", True):
            out.append(f"ratchet: slice {old['name']} is no longer blocking")
    old_c = (base_spec.get("bootstrap") or {}).get("confidence")
    new_c = (spec.get("bootstrap") or {}).get("confidence")
    if old_c is not None and (new_c is None or new_c > old_c):
        out.append(f"ratchet: bootstrap confidence {old_c} -> {new_c} widens the CI")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "fail"            # an empty slice is not a passing slice: nothing was measured
            note = "no graded rows in PR"
        else:
            val = sum(a.values()) / len(a)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking", True):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if sl.get("blocking", True) else "warn")
        shown = "-" if val is None else f"{val:.4f}"
        th = json.dumps({k: sl[k] for k in ("min", "no_significant_drop") if k in sl})
        lines.append(f"  {sid:<34} {shown:<8} {th:<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
