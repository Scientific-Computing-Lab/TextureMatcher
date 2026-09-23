#!/usr/bin/env python3
"""Score-only reproduction of every file-traceable table and macro.

Reads cached Inception-v3 / DINOv2 feature caches and per-pair CSVs from the
results archive (no CNT, no rendering, no GPU) and:

  1. Recomputes every absolute KID with the trace-corrected reference term
     (see texton_matching.scoring for why this matters -- the paper's own
     absolute-KID macros were only ever *printed*, in jackknife_dKID.ipynb
     cell 5 and presubmission_additions.ipynb cell 6; no file in the archive
     stores them).
  2. Recomputes every FID.
  3. Recomputes every paired leave-one-pair-out jackknife Delta-KID and its
     95% CI.
  4. Recomputes realism (real_inc, real_dino) and balance from the per-pair
     CSVs the notebooks already wrote (these are not affected by the KID
     bug, so they are read as median(per-pair value), matching the paper's
     own aggregation, not re-derived from raw manifold radii).
  5. Compares every one of the above to the macro value in
     paper/numbers.tex / paper/numbers_v2.tex and writes CHECK.md.
  6. Writes corrected versions of the stale-KID summary tables into
     package/evidence/ (does not touch data/).

Runs in a couple of minutes on CPU. Usage:

    python score_only.py [--data-root PATH] [--paper-root PATH]

--paper-root is the folder containing numbers.tex and numbers_v2.tex.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from texton_matching.paths import pairs_dir, resolve_data_root
from texton_matching.scoring import (
    balance_from_place,
    fid_score,
    kid_full,
    kid_subsampled,
    paired_jackknife_delta_kid,
)

PACKAGE_ROOT = Path(__file__).resolve().parent
# Folder holding the paper's macro files numbers.tex and numbers_v2.tex. The
# frozen copy shipped in evidence/paper_numbers/ is the default, so Tier 1 runs
# from this repository alone; pass --paper-root to compare against another copy.
DEFAULT_PAPER_ROOT = PACKAGE_ROOT / "evidence" / "paper_numbers"


# ---------------------------------------------------------------------------
# Macro parsing (read-only; paper/ is never written to)
# ---------------------------------------------------------------------------

def load_macros(paper_root: Path) -> dict[str, str]:
    src = (paper_root / "numbers.tex").read_text() + "\n" + (paper_root / "numbers_v2.tex").read_text()
    macros: dict[str, str] = {}
    for m in re.finditer(r"\\newcommand\{\\(\w+)\}\{", src):
        i = m.end()
        depth = 1
        j = i
        while depth:
            c = src[j]
            depth += (c == "{") - (c == "}")
            j += 1
        val = src[i : j - 1]
        for a, b in [
            ("\\!\\times\\!", "x"),
            ("{,}", ","),
            ("\\%", "%"),
            ("$-$", "-"),
            ("\\pm", "+/-"),
            ("\\,", ""),
        ]:
            val = val.replace(a, b)
        macros[m.group(1)] = val
    return macros


def parse_num(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = raw.strip()
    is_pct = s.endswith("%")
    s = s.rstrip("%").replace(",", "")
    m = re.search(r"-?\d+\.?\d*", s)
    if not m:
        return None
    v = float(m.group(0))
    return v  # percent macros are compared in "percent units" throughout


def parse_ci(raw: str | None) -> tuple[float, float] | None:
    if raw is None:
        return None
    m = re.search(r"\[([^,\]]+),\s*\+?([^\]]+)\]", raw)
    if not m:
        return None
    lo = parse_num(m.group(1))
    hi = parse_num(m.group(2))
    if lo is None or hi is None:
        return None
    return lo, hi


# ---------------------------------------------------------------------------
# CHECK.md row bookkeeping
# ---------------------------------------------------------------------------

ROWS: list[dict] = []


def check(macro: str, paper_val, computed_val, *, source: str, table: str, rel_tol: float = 0.02, abs_tol: float = 0.0006):
    """Record one macro <-> recomputed-value comparison."""
    if computed_val is not None and isinstance(computed_val, (float, np.floating)) and np.isnan(computed_val):
        computed_val = None  # e.g. .median() of an empty per-pair slice -> no file row, not a numeric miss
    if paper_val is None or computed_val is None:
        status = "NO PAPER VALUE" if paper_val is None else "NO FILE ROW"
        delta = None
    else:
        delta = computed_val - paper_val
        tol = max(abs_tol, rel_tol * abs(paper_val))
        status = "MATCH" if abs(delta) <= tol else "MISMATCH"
    ROWS.append(
        dict(table=table, macro=macro, paper=paper_val, computed=computed_val, delta=delta, status=status, source=source)
    )


def check_ci(macro: str, paper_ci, computed: "object", *, source: str, table: str, abs_tol: float = 0.0006):
    """Compare a (dKID, lo, hi) computed result against a macro + macroCI pair."""
    paper_delta, paper_lo, paper_hi = paper_ci
    if computed is None:
        for suf, pv in [("", paper_delta), ("CI.lo", paper_lo), ("CI.hi", paper_hi)]:
            check(macro + suf, pv, None, source=source, table=table)
        return
    check(macro, paper_delta, computed.delta, source=source, table=table, abs_tol=abs_tol)
    check(macro + "CI.lo", paper_lo, computed.lo, source=source, table=table, abs_tol=abs_tol)
    check(macro + "CI.hi", paper_hi, computed.hi, source=source, table=table, abs_tol=abs_tol)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--paper-root", default=str(DEFAULT_PAPER_ROOT))
    ap.add_argument("--out-dir", default=str(PACKAGE_ROOT))
    args = ap.parse_args()

    data = resolve_data_root(args.data_root)
    paper_root = Path(args.paper_root)
    out_dir = Path(args.out_dir)
    evidence_dir = out_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    M = load_macros(paper_root)
    print(f"[score_only] data root: {data}")
    print(f"[score_only] {len(M)} macros parsed from {paper_root}")

    # The one frozen reference used everywhere from mid-August on: 2,819 DTD
    # images, 60/category, seed 2819 (matching_ablation/ref_list.json).
    ref_inc = np.load(data / "matching_ablation" / "ref_inc.npy")
    ref_dino = np.load(data / "matching_ablation" / "ref_dino.npy")
    assert len(ref_inc) == 2819 and len(ref_dino) == 2819, "reference set size drifted from the expected 2,819"

    ks120 = sorted(pd.read_csv(pairs_dir(data) / "pairs.csv")["k"].tolist())
    assert len(ks120) == 120

    # =====================================================================
    # Table 1, CNT block (n=1,000, 128px) -- finish_day.ipynb cell 2 (rescore)
    #   + cell 10 (Gaussian W2 row).
    # =====================================================================
    t1 = data / "matching_ablation" / "final128_n1000.csv"
    d1000 = pd.read_csv(t1)
    d1000["bal"] = balance_from_place(d1000["place"])
    method_feat = {
        "pixel_linear": "Pixel", "texton_linear": "Position", "gaussian_w2": "Gaussian",
        "ot": "Transport", "exact": "Hard", "ot_sym": "Symmetric", "tm": "Mixer",
    }
    t1_corrected = []
    for method, macsuf in method_feat.items():
        inc_path = data / "matching_ablation" / f"feat_{method}_inc.npy"
        if not inc_path.exists():
            continue
        gen = np.load(inc_path)
        # finish_day's own kid() helper subsamples both sides (n_sub=1000,
        # n_rep=20) rather than using the full 2,819-image reference in one
        # pass; the two trace-corrected estimators agree to within noise, but
        # matching the exact source formula here removes that noise for the
        # one row (ot_sym) close enough to the default tolerance to matter.
        kid = kid_subsampled(gen, ref_inc, n_sub=1000, n_rep=20, seed=0)
        fid = fid_score(gen, ref_inc)
        sub = d1000[d1000.method == method]
        rinc = sub.real_inc.median() if len(sub) else None
        bal = sub.bal.median() if len(sub) else None
        rdin = sub.real_dino.median() if len(sub) else None
        check(f"KID{macsuf}", parse_num(M.get(f"KID{macsuf}")), kid, source=str(t1.relative_to(data)) + " (+recompute, subsampled KID)", table="Table1-CNT-1000")
        check(f"FID{macsuf}", parse_num(M.get(f"FID{macsuf}")), fid, source=str(t1.relative_to(data)) + " (+recompute)", table="Table1-CNT-1000")
        check(f"Inc{macsuf}", parse_num(M.get(f"Inc{macsuf}")), rinc, source=str(t1.relative_to(data)), table="Table1-CNT-1000")
        check(f"Place{macsuf}", parse_num(M.get(f"Place{macsuf}")), bal, source=str(t1.relative_to(data)), table="Table1-CNT-1000")
        check(f"DINO{macsuf}", parse_num(M.get(f"DINO{macsuf}")), rdin, source=str(t1.relative_to(data)), table="Table1-CNT-1000")
        t1_corrected.append(dict(method=method, KID=kid, FID=fid, RInc=rinc, RDin=rdin, Bal=bal))

    # Table 1 percent-improvement column (derived arithmetic on the KIDs above)
    kid_pix = parse_num(M.get("KIDPixel"))
    for macro, other in [("CKIDpctGauss", "KIDGaussian"), ("CKIDpctOT", "KIDTransport")]:
        v = parse_num(M.get(other))
        pct = None if (kid_pix is None or v is None) else 100 * (kid_pix - v) / kid_pix
        check(macro, parse_num(M.get(macro)), pct, source="derived from KIDPixel/" + other, table="Table1-CNT-1000", rel_tol=0.05, abs_tol=0.6)
    v = parse_num(M.get("KIDHard"))
    pct = None if (kid_pix is None or v is None) else -100 * (v - kid_pix) / kid_pix
    check("CKIDpctExact", parse_num(M.get("CKIDpctExact")), pct, source="derived from KIDPixel/KIDHard", table="Table1-CNT-1000", rel_tol=0.05, abs_tol=0.6)

    pd.DataFrame(t1_corrected).to_csv(evidence_dir / "table1_cnt_1000_corrected.csv", index=False)

    # numbers_v2 GFIDotsym/GKIDotsym etc. are the 120-pair subset of the
    # 1,000-pair ot_sym cache (verified during construction: matches exactly).
    otsym_inc = np.load(data / "matching_ablation" / "feat_ot_sym_inc.npy")[ks120]
    sub_otsym = d1000[(d1000.method == "ot_sym") & (d1000.k.isin(ks120))]
    check("GFIDotsym", parse_num(M.get("GFIDotsym")), fid_score(otsym_inc, ref_inc), source="feat_ot_sym_inc.npy[k in pairs_120] (+recompute)", table="Table-generative-120")
    check("GKIDotsym", parse_num(M.get("GKIDotsym")), kid_full(otsym_inc, ref_inc), source="feat_ot_sym_inc.npy[k in pairs_120] (+recompute)", table="Table-generative-120")
    check("GRIncotsym", parse_num(M.get("GRIncotsym")), sub_otsym.real_inc.median() if len(sub_otsym) else None, source="final128_n1000.csv[k in pairs_120]", table="Table-generative-120")
    check("GRDinotsym", parse_num(M.get("GRDinotsym")), sub_otsym.real_dino.median() if len(sub_otsym) else None, source="final128_n1000.csv[k in pairs_120]", table="Table-generative-120")
    check("GPlaceotsym", parse_num(M.get("GPlaceotsym")), (sub_otsym.place - 0.5).abs().median() if len(sub_otsym) else None, source="final128_n1000.csv[k in pairs_120]", table="Table-generative-120")

    # =====================================================================
    # Table 1, Texture Mixer block (n=1,000) -- presubmission_additions cell 6
    # =====================================================================
    tm_rule_macro = {"lerp": "lerp", "mean": "mean", "ot_r0.03": "ot"}
    for rule, msuf in tm_rule_macro.items():
        feats = np.load(data / "jackknife" / f"feats_tm1000_{rule}.npy")
        scores = pd.read_csv(data / "jackknife" / f"scores_tm1000_{rule}.csv")
        kid = kid_full(feats, ref_inc)
        fid = fid_score(feats, ref_inc)
        bal = np.median(balance_from_place(scores["place"]))
        check(f"TMkKID{msuf}", parse_num(M.get(f"TMkKID{msuf}")), kid, source="jackknife/feats_tm1000_*.npy (+recompute)", table="Table1-TM-1000")
        check(f"TMkRInc{msuf}", parse_num(M.get(f"TMkRInc{msuf}")), scores.real_inc.median(), source="jackknife/scores_tm1000_*.csv", table="Table1-TM-1000")
        check(f"TMkBal{msuf}", parse_num(M.get(f"TMkBal{msuf}")), bal, source="jackknife/scores_tm1000_*.csv", table="Table1-TM-1000")
    feats_lerp = np.load(data / "jackknife" / "feats_tm1000_lerp.npy")
    feats_mean = np.load(data / "jackknife" / "feats_tm1000_mean.npy")
    feats_ot = np.load(data / "jackknife" / "feats_tm1000_ot_r0.03.npy")
    r = paired_jackknife_delta_kid(feats_mean, feats_lerp, ref_inc)
    check_ci("TMkdKIDmean", (parse_num(M.get("TMkdKIDmean")), *(parse_ci(M.get("TMkdKIDmeanCI")) or (None, None))), r, source="jackknife/feats_tm1000_*.npy (+recompute)", table="Table1-TM-1000")
    r = paired_jackknife_delta_kid(feats_ot, feats_lerp, ref_inc)
    check_ci("TMkdKIDot", (parse_num(M.get("TMkdKIDot")), *(parse_ci(M.get("TMkdKIDotCI")) or (None, None))), r, source="jackknife/feats_tm1000_*.npy (+recompute)", table="Table1-TM-1000")
    r = paired_jackknife_delta_kid(feats_ot, feats_mean, ref_inc)
    check_ci("TMkdKIDotVsMean", (parse_num(M.get("TMkdKIDotVsMean")), *(parse_ci(M.get("TMkdKIDotVsMeanCI")) or (None, None))), r, source="jackknife/feats_tm1000_*.npy (+recompute)", table="Table1-TM-1000")

    kid_lerp = kid_full(feats_lerp, ref_inc)
    kid_mean = kid_full(feats_mean, ref_inc)
    kid_ot = kid_full(feats_ot, ref_inc)
    check("TMkKIDgain", parse_num(M.get("TMkKIDgain")), 100 * (kid_lerp - kid_mean) / kid_lerp, source="derived (mean vs lerp)", table="Table1-TM-1000", rel_tol=0.05, abs_tol=0.6)
    check("TMkKIDpctOT", parse_num(M.get("TMkKIDpctOT")), 100 * (kid_lerp - kid_ot) / kid_lerp, source="derived (ot vs lerp)", table="Table1-TM-1000", rel_tol=0.05, abs_tol=0.6)

    # FID of the Texture Mixer block (Table 1 has no FID macros for it yet):
    # the same fid_score as every other FID here, against the canonical
    # reference. Written to evidence/paper_numbers/numbers_tmfid.tex as
    # proposed macros; not read back as paper values.
    tm_fid = {"lerp": fid_score(feats_lerp, ref_inc), "mean": fid_score(feats_mean, ref_inc), "ot": fid_score(feats_ot, ref_inc)}
    tmfid_lines = []
    for key, val in tm_fid.items():
        macro = f"TMkFID{key}"
        tmfid_lines.append(f"\\newcommand{{\\{macro}}}{{{val:.1f}}}")
        ROWS.append(dict(table="Table1-TM-1000", macro=macro, paper=None, computed=val, delta=None,
                         status="INFO (new; no paper macro yet)", source="jackknife/feats_tm1000_*.npy vs matching_ablation/ref_inc.npy (+recompute, fid_score)"))
    (evidence_dir / "paper_numbers").mkdir(parents=True, exist_ok=True)
    (evidence_dir / "paper_numbers" / "numbers_tmfid.tex").write_text(
        "% Texture Mixer FID, Table 1 (1,000 pairs, canonical Inception reference), generated by score_only.py.\n"
        + "\n".join(tmfid_lines) + "\n")
    print("\n".join(tmfid_lines))

    pd.DataFrame(
        [dict(rule=r_, KID=kid_full(np.load(data / "jackknife" / f"feats_tm1000_{r_}.npy"), ref_inc)) for r_ in tm_rule_macro]
    ).to_csv(evidence_dir / "table1_tm_1000_corrected.csv", index=False)

    # =====================================================================
    # tab:eqsample (200 pairs, matched rendering) -- jackknife_dKID cell 4/5
    # =====================================================================
    eq_rule_macro = {
        "linear_cp": "linear", "hard": "hard", "ot_e0.005": "otSharp",
        "ot_e0.05": "ot", "ot_paper": "paper",
    }
    eq_feats = {}
    eq_corrected = []
    for rule, msuf in eq_rule_macro.items():
        feats = np.load(data / "jackknife" / f"feats_eq_{rule}.npy")
        eq_feats[rule] = feats
        kid = kid_full(feats, ref_inc)
        fid = fid_score(feats, ref_inc)
        check(f"EqKID{msuf}", parse_num(M.get(f"EqKID{msuf}")), kid, source="jackknife/feats_eq_*.npy (+recompute)", table="tab:eqsample")
        check(f"EqFID{msuf}", parse_num(M.get(f"EqFID{msuf}")), fid, source="jackknife/feats_eq_*.npy (+recompute)", table="tab:eqsample")
        if rule != "ot_paper":
            scores = pd.read_csv(data / "jackknife" / f"scores_eq_{rule}.csv")
            bal = np.median(balance_from_place(scores["place"]))
            check(f"EqBal{msuf}", parse_num(M.get(f"EqBal{msuf}")), bal, source="jackknife/scores_eq_*.csv", table="tab:eqsample")
            check(f"EqRInc{msuf}", parse_num(M.get(f"EqRInc{msuf}")), scores.real_inc.median(), source="jackknife/scores_eq_*.csv", table="tab:eqsample")
        eq_corrected.append(dict(rule=rule, KID=kid, FID=fid))
    # ot_paper's Bal/RInc are in eqsample_summary.csv (the 4096-sample row
    # has no per-pair scores_eq_*.csv of its own in the archive).
    eqsumm = pd.read_csv(data / "evidence" / "eqsample_summary.csv").set_index("rule")
    if "ot_4096 (paper)" in eqsumm.index:
        pass  # KID/FID already checked above from features; Bal/RInc for
              # this row are not separately cached per-pair -- left to the
              # file-level summary (see NOT-RECOMPUTED section).
    for rule, msuf in [("hard", "hard"), ("ot_e0.005", "otSharp"), ("ot_e0.05", "ot")]:
        if rule in eqsumm.index:
            check(f"EqGap{msuf}", parse_num(M.get(f"EqGap{msuf}")), eqsumm.loc[rule, "t1_target_gap"], source="evidence/eqsample_summary.csv", table="tab:eqsample")
    check("EqVarRetSharp", parse_num(M.get("EqVarRetSharp")), eqsumm.loc["ot_e0.005", "var_ret"] if "ot_e0.005" in eqsumm.index else None, source="evidence/eqsample_summary.csv", table="tab:eqsample")
    check("EqVarRet", parse_num(M.get("EqVarRet")), eqsumm.loc["ot_e0.05", "var_ret"] if "ot_e0.05" in eqsumm.index else None, source="evidence/eqsample_summary.csv", table="tab:eqsample")

    pairs = [
        ("EqdKIDotVsLinear", "ot_e0.05", "linear_cp"),
        ("EqdKIDotPaperVsLinear", "ot_paper", "linear_cp"),
        ("EqdKIDhardVsLinear", "hard", "linear_cp"),
        ("EqdKIDhard", "hard", "ot_e0.05"),
        ("EqdKIDhardSharp", "hard", "ot_e0.005"),
        ("EqdKIDsharp", "ot_e0.005", "ot_e0.05"),
    ]
    for macro, b, a in pairs:
        r = paired_jackknife_delta_kid(eq_feats[b], eq_feats[a], ref_inc)
        check_ci(macro, (parse_num(M.get(macro)), *(parse_ci(M.get(macro + "CI")) or (None, None))), r, source="jackknife/feats_eq_*.npy (+recompute)", table="tab:eqsample")

    kid_lin = kid_full(eq_feats["linear_cp"], ref_inc)
    kid_ot05 = kid_full(eq_feats["ot_e0.05"], ref_inc)
    kid_paper = kid_full(eq_feats["ot_paper"], ref_inc)
    fid_lin = fid_score(eq_feats["linear_cp"], ref_inc)
    fid_paper = fid_score(eq_feats["ot_paper"], ref_inc)
    check("EqKIDgainOT", parse_num(M.get("EqKIDgainOT")), 100 * (kid_lin - kid_paper) / kid_lin, source="derived (paper vs linear)", table="tab:eqsample", rel_tol=0.05, abs_tol=0.6)
    check("EqFIDgainOT", parse_num(M.get("EqFIDgainOT")), 100 * (fid_lin - fid_paper) / fid_lin, source="derived (paper vs linear)", table="tab:eqsample", rel_tol=0.05, abs_tol=0.6)
    check("EqKIDgainOTsmall", parse_num(M.get("EqKIDgainOTsmall")), 100 * (kid_lin - kid_ot05) / kid_lin, source="derived (4096-sample ot_e0.05 vs linear)", table="tab:eqsample", rel_tol=0.05, abs_tol=0.6)

    pd.DataFrame(eq_corrected).to_csv(evidence_dir / "table200_eqsample_corrected.csv", index=False)

    # Actual p-values behind \EqBalP / \EqGapP (paper states p < 10^-14 / 10^-13)
    from scipy.stats import wilcoxon
    hard_scores = pd.read_csv(data / "jackknife" / "scores_eq_hard.csv")
    ot05_scores = pd.read_csv(data / "jackknife" / "scores_eq_ot_e0.05.csv")
    bal_hard = balance_from_place(hard_scores["place"])
    bal_ot = balance_from_place(ot05_scores["place"])
    p_bal = wilcoxon(bal_hard, bal_ot).pvalue
    ROWS.append(dict(table="tab:eqsample", macro="EqBalP (actual p)", paper=parse_num(M.get("EqBalP")), computed=p_bal,
                      delta=None, status="SEE NOTE: paper says p<value, actual p=%.2e" % p_bal,
                      source="jackknife/scores_eq_{hard,ot_e0.05}.csv (+recompute, paired Wilcoxon)"))

    # =====================================================================
    # tab:generative / tab:app-generative (120 pairs)
    # =====================================================================
    g_rule_macro = {
        "pix": "pix", "tex": "tex", "gauss": "gauss", "ot": "ot", "hard": "hard",
        "tm": "tm", "gpt": "gpt", "gptsym": "gptsym",
    }
    g_feats = {}
    g_corrected = []
    for rule, msuf in g_rule_macro.items():
        feats = np.load(data / "jackknife" / f"feats_g_{rule}.npy")
        g_feats[rule] = feats
        scores = pd.read_csv(data / "jackknife" / f"scores_g_{rule}.csv")
        kid = kid_full(feats, ref_inc)
        fid = fid_score(feats, ref_inc)
        bal = np.median(balance_from_place(scores["place"]))
        check(f"GKID{msuf}", parse_num(M.get(f"GKID{msuf}")), kid, source="jackknife/feats_g_*.npy (+recompute)", table="tab:generative-120")
        check(f"GFID{msuf}", parse_num(M.get(f"GFID{msuf}")), fid, source="jackknife/feats_g_*.npy (+recompute)", table="tab:generative-120")
        check(f"GRInc{msuf}", parse_num(M.get(f"GRInc{msuf}")), scores.real_inc.median(), source="jackknife/scores_g_*.csv", table="tab:generative-120")
        check(f"GRDin{msuf}", parse_num(M.get(f"GRDin{msuf}")), scores.real_dino.median(), source="jackknife/scores_g_*.csv", table="tab:generative-120")
        check(f"GPlace{msuf}", parse_num(M.get(f"GPlace{msuf}")), bal, source="jackknife/scores_g_*.csv", table="tab:generative-120")
        g_corrected.append(dict(rule=rule, KID=kid, FID=fid, RInc=scores.real_inc.median(), RDin=scores.real_dino.median(), Bal=bal))

    tm_rule2_macro = {"tmlerp": "lerp", "tmmean": "mean", "tmot": "ot", "tmhard": "hard"}
    for rule, msuf in tm_rule2_macro.items():
        feats = np.load(data / "jackknife" / f"feats_g_{rule}.npy")
        g_feats[rule] = feats
        scores = pd.read_csv(data / "jackknife" / f"scores_g_{rule}.csv")
        kid = kid_full(feats, ref_inc)
        fid = fid_score(feats, ref_inc)
        bal = np.median(balance_from_place(scores["place"]))
        check(f"TMKID{msuf}", parse_num(M.get(f"TMKID{msuf}")), kid, source="jackknife/feats_g_*.npy (+recompute)", table="tab:generative-120")
        check(f"TMFID{msuf}", parse_num(M.get(f"TMFID{msuf}")), fid, source="jackknife/feats_g_*.npy (+recompute)", table="tab:generative-120")
        check(f"TMRInc{msuf}", parse_num(M.get(f"TMRInc{msuf}")), scores.real_inc.median(), source="jackknife/scores_g_*.csv", table="tab:generative-120")
        check(f"TMRDin{msuf}", parse_num(M.get(f"TMRDin{msuf}")), scores.real_dino.median(), source="jackknife/scores_g_*.csv", table="tab:generative-120")
        check(f"TMBal{msuf}", parse_num(M.get(f"TMBal{msuf}")), bal, source="jackknife/scores_g_*.csv", table="tab:generative-120")
        g_corrected.append(dict(rule=rule, KID=kid, FID=fid, RInc=scores.real_inc.median(), RDin=scores.real_dino.median(), Bal=bal))

    r = paired_jackknife_delta_kid(g_feats["ot"], g_feats["pix"], ref_inc)
    check_ci("GdKIDotVsPix", (parse_num(M.get("GdKIDotVsPix")), *(parse_ci(M.get("GdKIDotVsPixCI")) or (None, None))), r, source="jackknife/feats_g_*.npy (+recompute)", table="tab:generative-120")
    r = paired_jackknife_delta_kid(g_feats["tmmean"], g_feats["tmlerp"], ref_inc)
    check_ci("TMdKIDmean", (parse_num(M.get("TMdKIDmean")), *(parse_ci(M.get("TMdKIDmeanCI")) or (None, None))), r, source="jackknife/feats_g_*.npy (+recompute)", table="tab:generative-120")
    r = paired_jackknife_delta_kid(g_feats["tmot"], g_feats["tmlerp"], ref_inc)
    check_ci("TMdKIDot", (parse_num(M.get("TMdKIDot")), *(parse_ci(M.get("TMdKIDotCI")) or (None, None))), r, source="jackknife/feats_g_*.npy (+recompute)", table="tab:generative-120")
    r = paired_jackknife_delta_kid(g_feats["tmhard"], g_feats["tmlerp"], ref_inc)
    check_ci("TMdKIDhard", (parse_num(M.get("TMdKIDhard")), *(parse_ci(M.get("TMdKIDhardCI")) or (None, None))), r, source="jackknife/feats_g_*.npy (+recompute)", table="tab:generative-120")
    r = paired_jackknife_delta_kid(g_feats["tmot"], g_feats["tmmean"], ref_inc)
    check_ci("TMdKIDotVsMean", (parse_num(M.get("TMdKIDotVsMean")), *(parse_ci(M.get("TMdKIDotVsMeanCI")) or (None, None))), r, source="jackknife/feats_g_*.npy (+recompute)", table="tab:generative-120")

    kid_pix120 = kid_full(g_feats["pix"], ref_inc)
    kid_tmlerp120 = kid_full(g_feats["tmlerp"], ref_inc)
    kid_tmmean120 = kid_full(g_feats["tmmean"], ref_inc)
    kid_tmot120 = kid_full(g_feats["tmot"], ref_inc)
    check("TMKIDgainMean", parse_num(M.get("TMKIDgainMean")), 100 * (kid_tmlerp120 - kid_tmmean120) / kid_tmlerp120, source="derived", table="tab:generative-120", rel_tol=0.05, abs_tol=0.6)
    check("TMKIDgainOT", parse_num(M.get("TMKIDgainOT")), 100 * (kid_tmlerp120 - kid_tmot120) / kid_tmlerp120, source="derived", table="tab:generative-120", rel_tol=0.05, abs_tol=0.6)

    pd.DataFrame(g_corrected).to_csv(evidence_dir / "table120_generative_corrected.csv", index=False)

    # =====================================================================
    # tab:rules (200 pairs, original rendering protocol) -- matching_ablation
    # =====================================================================
    rules_feats = np.load(data / "matching_ablation" / "rules_feats.npz")
    rules_n200 = pd.read_csv(data / "matching_ablation" / "rules_n200.csv")
    rule_name_macro = {
        "random": "Random", "uniform": "Mean", "pixel_linear": "Pixel", "texton_linear": "Position",
        "gauss": "Gaussian", "nn": "NN", "exact": "Hard", "ot": "Transport", "ot_sharp": "Sharp",
    }
    idxs = sorted(set(int(k.split("_")[0]) for k in rules_feats.keys()))
    rules_corrected = []
    for rule, msuf in rule_name_macro.items():
        gen_inc = np.stack([rules_feats[f"{i}_{rule}_inc"] for i in idxs])
        # matching_ablation.ipynb / exact_finish.ipynb wrote kid_by_rule.json
        # with the same subsampled estimator as Table 1 (m = min(1000, 200,
        # 2819) = 200 here, so this call is equivalent to a single full pass,
        # but kept explicit for consistency with the source formula).
        kid = kid_subsampled(gen_inc, ref_inc, n_sub=1000, n_rep=20, seed=0)
        fid = fid_score(gen_inc, ref_inc)
        check(f"RuleKID{msuf}", parse_num(M.get(f"RuleKID{msuf}")), kid, source="matching_ablation/rules_feats.npz (+recompute, subsampled KID)", table="tab:rules-200")
        check(f"RuleFID{msuf}", parse_num(M.get(f"RuleFID{msuf}")), fid, source="matching_ablation/rules_feats.npz (+recompute)", table="tab:rules-200")
        rules_corrected.append(dict(rule=rule, KID=kid, FID=fid))
    sub = rules_n200[rules_n200.rule == "random"]
    check("RandomIncRealism", parse_num(M.get("RandomIncRealism")), sub.real_inc.median(), source="matching_ablation/rules_n200.csv", table="tab:rules-200")
    check("RandomDINORealism", parse_num(M.get("RandomDINORealism")), sub.real_dino.median(), source="matching_ablation/rules_n200.csv", table="tab:rules-200")
    # inline gap/balance values quoted in prose for nn / exact / ot rows
    for rule, label in [("nn", "NN"), ("exact", "Hard/Exact"), ("ot", "Soft-OT")]:
        sub = rules_n200[rules_n200.rule == rule]
        bal = np.median(balance_from_place(sub["place"]))
        gap = sub["endpoint_gap"].median()
        ROWS.append(dict(table="tab:rules-200", macro=f"(inline) {label} balance", paper=None, computed=bal, delta=None, status="INFO (b={:.3f}, gap={:.3f}; see supplement.tex prose)".format(bal, gap), source="matching_ablation/rules_n200.csv"))

    for macro, colname in [("MeanRealismDelta", "uniform"), ("RandomRealismDelta", "random"), ("HardRealismDelta", "exact")]:
        sub_other = rules_n200[rules_n200.rule == colname].set_index("k")["real_inc"]
        sub_ot = rules_n200[rules_n200.rule == "ot"].set_index("k")["real_inc"]
        delta = (sub_other - sub_ot).median()
        # bootstrap CI of the median difference, matched-pairs
        rng = np.random.RandomState(0)
        diffs = (sub_other - sub_ot).values
        boots = [np.median(rng.choice(diffs, len(diffs), replace=True)) for _ in range(2000)]
        lo, hi = np.percentile(boots, [2.5, 97.5])
        check(macro, parse_num(M.get(macro)), delta, source="matching_ablation/rules_n200.csv (+recompute, paired median)", table="tab:rules-200", abs_tol=0.003)
        # numbers_v2.tex names these <Macro>CI, not <Macro>DeltaCI (drop "Delta")
        ci_macro = macro.replace("Delta", "") + "CI"
        pci = parse_ci(M.get(ci_macro))
        check(macro + "CI.lo", pci[0] if pci else None, lo, source="matching_ablation/rules_n200.csv (+bootstrap, seed varies)", table="tab:rules-200", abs_tol=0.01)
        check(macro + "CI.hi", pci[1] if pci else None, hi, source="matching_ablation/rules_n200.csv (+bootstrap, seed varies)", table="tab:rules-200", abs_tol=0.01)

    pd.DataFrame(rules_corrected).to_csv(evidence_dir / "table200_rules_corrected.csv", index=False)

    # =====================================================================
    # tab:app-primitives + primitive prose (120 pairs) -- CNT_correspondence
    # =====================================================================
    corr_feats = np.load(data / "correspondence" / "feats" / "E1.npz")
    corr4_feats = np.load(data / "correspondence" / "feats" / "E4.npz")
    corr_dense_feats = np.load(data / "correspondence" / "feats" / "dense.npz")

    def stack_arm(npz, arm, feat="inc", n=120):
        keys = sorted((k for k in npz.keys() if k.startswith(arm + "|") and k.endswith("|" + feat)),
                      key=lambda k: int(k.split("|")[1]))
        return np.stack([npz[k] for k in keys])

    arms = {"P_morph": "GEKIDmorphP", "A_morph": "GEKIDmorphA", "P_fixA": "GEKIDfixP",
            "A_fixA": "GEKIDfixA", "PA_fixA": "GEKIDfixPA"}
    prim_corrected = []
    prim_arrays = {}
    for arm, macro in arms.items():
        gen = stack_arm(corr_feats, arm)
        prim_arrays[arm] = gen
        kid = kid_full(gen, ref_inc)
        check(macro, parse_num(M.get(macro)), kid, source="correspondence/feats/E1.npz (+recompute)", table="tab:app-primitives-120")
        prim_corrected.append(dict(arm=arm, KID=kid))

    r = paired_jackknife_delta_kid(prim_arrays["A_morph"], prim_arrays["P_morph"], ref_inc)
    check_ci("GEdKIDmorph", (parse_num(M.get("GEdKIDmorph")), *(parse_ci(M.get("GEdKIDmorphCI")) or (None, None))), r, source="correspondence/feats/E1.npz (+recompute)", table="tab:app-primitives-120")
    r = paired_jackknife_delta_kid(prim_arrays["A_fixA"], prim_arrays["P_fixA"], ref_inc)
    check_ci("GEdKIDfix", (parse_num(M.get("GEdKIDfix")), *(parse_ci(M.get("GEdKIDfixCI")) or (None, None))), r, source="correspondence/feats/E1.npz (+recompute)", table="tab:app-primitives-120")

    gen_soft = stack_arm(corr4_feats, "gA_sink1.0_fixA")  # eps_match=1.0, the row matched to dense OT's variance
    gen_dense = stack_arm(corr_dense_feats, "ot")  # the dense-OT baseline lives in dense.npz, not E4.npz
    check("GEKIDprimSoft", parse_num(M.get("GEKIDprimSoft")), kid_full(gen_soft, ref_inc), source="correspondence/feats/E4.npz (+recompute)", table="tab:app-primitives-120")
    check("GEKIDdenseOT", parse_num(M.get("GEKIDdenseOT")), kid_full(gen_dense, ref_inc), source="correspondence/feats/E4.npz (+recompute)", table="tab:app-primitives-120")
    check("GEKIDprimHard", parse_num(M.get("GEKIDprimHard")), kid_full(prim_arrays["P_fixA"], ref_inc), source="correspondence/feats/E1.npz (+recompute, one-to-one position row)", table="tab:app-primitives-120")

    pd.DataFrame(prim_corrected).to_csv(evidence_dir / "primitives_120_corrected.csv", index=False)

    # =====================================================================
    # app:ceiling (120 pairs) -- CNT_joint_basis_and_ceiling cell 5
    #
    # This notebook scores against its OWN reference: the full 5,640-image
    # DTD set at native 128px windows (ref_inc_win128.npy), not the
    # 2,819-image canonical reference used everywhere else. Confirmed during
    # construction: KID against the canonical 2,819 reference is ~150x too
    # small (it is comparing two near-identical real-image samples), while
    # KID against ref_inc_win128 reproduces the paper macros exactly.
    # =====================================================================
    ceil_feats = np.load(data / "joint_basis" / "feats_ceiling.npz")
    ref_inc_win128 = np.load(data / "joint_basis" / "ref_inc_win128.npy")
    assert len(ref_inc_win128) == 5640

    def stack_ceiling(what, feat="inc"):
        keys = sorted((k for k in ceil_feats.keys() if k.split("|")[1] == what and k.endswith("|" + feat)),
                      key=lambda k: (k.split("|")[0], int(k.split("|")[2])))
        return np.stack([ceil_feats[k] for k in keys])

    ceil_corrected = []
    for what, msuf in [("orig", "orig"), ("rec1", "rec"), ("rec2", "recTwo")]:
        gen = stack_ceiling(what)
        kid = kid_full(gen, ref_inc_win128)
        check(f"CeilKID{msuf}", parse_num(M.get(f"CeilKID{msuf}")), kid, source="joint_basis/feats_ceiling.npz vs ref_inc_win128.npy (+recompute)", table="app:ceiling-120", abs_tol=0.0008)
        ceil_corrected.append(dict(what=what, KID=kid, n=len(gen)))
    mid_ot120 = np.load(data / "jackknife" / "feats_g_ot.npy")  # 120-pair ot midpoints, the ceiling's "midpoint_ot"
    kid_mid = kid_full(mid_ot120, ref_inc_win128)
    check("CeilKIDmid", parse_num(M.get("CeilKIDmid")), kid_mid, source="jackknife/feats_g_ot.npy vs joint_basis/ref_inc_win128.npy (+recompute)", table="app:ceiling-120", abs_tol=0.0008)
    ceil_corrected.append(dict(what="midpoint_ot", KID=kid_mid, n=len(mid_ot120)))
    pd.DataFrame(ceil_corrected).to_csv(evidence_dir / "ceiling_120_corrected.csv", index=False)

    ceiling_csv = pd.read_csv(data / "joint_basis" / "ceiling.csv")
    lpips_rec1 = ceiling_csv[ceiling_csv["what"] == "rec1"]["lpips_orig"].median()
    check("CeilLPIPSrec", parse_num(M.get("CeilLPIPSrec")), lpips_rec1, source="joint_basis/ceiling.csv", table="app:ceiling-120")

    # Realism here is per-pair (mean of A's and B's side, one value per pair)
    # not per-side -- that is what ceiling_summary.json's "decomposition"
    # already stores, at the exact 50th percentile the paper macros round.
    ceil_summary = json.load(open(data / "joint_basis" / "ceiling_summary.json"))
    decomp = ceil_summary["decomposition"]
    check("CeilRealOrig", parse_num(M.get("CeilRealOrig")), decomp["orig"]["50%"], source="joint_basis/ceiling_summary.json:decomposition.orig", table="app:ceiling-120", abs_tol=0.006)
    check("CeilRealRec", parse_num(M.get("CeilRealRec")), decomp["rec1"]["50%"], source="joint_basis/ceiling_summary.json:decomposition.rec1", table="app:ceiling-120", abs_tol=0.006)
    check("CeilRealMid", parse_num(M.get("CeilRealMid")), decomp["mid"]["50%"], source="joint_basis/ceiling_summary.json:decomposition.mid", table="app:ceiling-120", abs_tol=0.006)
    check("CeilRho", parse_num(M.get("CeilRho")), ceil_summary["spearman"]["rho_mid"], source="joint_basis/ceiling_summary.json:spearman.rho_mid (file value; recompute needs a per-pair reconstruction-error join, not attempted)", table="app:ceiling-120", abs_tol=0.006)

    # =====================================================================
    # fig:app-alignshift / the Align* macros -- finishing_experiments c8
    #
    # Added when experiments/alignment.py was built as this table's Tier-3
    # render script. Not previously checked at all (unlike tab:rules/
    # tab:app-primitives/app:ceiling, this had zero Tier-1 coverage before).
    # Aggregation (reverse-engineered from evidence/alignment_scores.csv and
    # cross-checked against finishing_experiments.ipynb c8's own printed
    # t=0.5 pivot table by the agent who wrote alignment.py): at t=0.5,
    # take the per-shift MEDIAN of dino_dev for a given rule, then:
    #   AlignLin{Zero,Sixteen,Max} = that per-shift median at shift={0,16,64}
    #   AlignGaussDev / AlignOTdev = MEAN of the per-shift medians across
    #     all four shifts {0,4,16,64} (not just one shift -- these two
    #     macros describe a shift-INDEPENDENT deviation, unlike the linear
    #     rows, which are reported per shift specifically to show the
    #     leak growing with shift).
    # AlignCrossLo/Hi (16, 64) are literal shift labels, not computed values.
    # =====================================================================
    align_scores = pd.read_csv(data / "evidence" / "alignment_scores.csv")
    align_t05 = align_scores[align_scores["t"] == 0.5]
    align_per_shift = {
        rule: align_t05[align_t05["rule"] == rule].groupby("shift")["dino_dev"].median()
        for rule in ("linear", "gauss", "ot")
    }
    check("AlignN", parse_num(M.get("AlignN")), align_scores["img"].nunique(), source="evidence/alignment_scores.csv", table="fig:app-alignshift")
    check("AlignLinZero", parse_num(M.get("AlignLinZero")), align_per_shift["linear"].get(0), source="evidence/alignment_scores.csv (+recompute, median dino_dev @t=0.5)", table="fig:app-alignshift")
    check("AlignLinSixteen", parse_num(M.get("AlignLinSixteen")), align_per_shift["linear"].get(16), source="evidence/alignment_scores.csv (+recompute, median dino_dev @t=0.5)", table="fig:app-alignshift")
    check("AlignLinMax", parse_num(M.get("AlignLinMax")), align_per_shift["linear"].get(64), source="evidence/alignment_scores.csv (+recompute, median dino_dev @t=0.5)", table="fig:app-alignshift")
    check("AlignGaussDev", parse_num(M.get("AlignGaussDev")), align_per_shift["gauss"].mean(), source="evidence/alignment_scores.csv (+recompute, mean of per-shift medians @t=0.5)", table="fig:app-alignshift")
    check("AlignOTdev", parse_num(M.get("AlignOTdev")), align_per_shift["ot"].mean(), source="evidence/alignment_scores.csv (+recompute, mean of per-shift medians @t=0.5)", table="fig:app-alignshift", abs_tol=0.001)
    ROWS.append(dict(table="fig:app-alignshift", macro="AlignCrossLo", paper=parse_num(M.get("AlignCrossLo")), computed=16, delta=None, status="INFO (literal shift label, not a computed value)", source="evidence/alignment_scores.csv"))
    ROWS.append(dict(table="fig:app-alignshift", macro="AlignCrossHi", paper=parse_num(M.get("AlignCrossHi")), computed=64, delta=None, status="INFO (literal shift label, not a computed value)", source="evidence/alignment_scores.csv"))

    # =====================================================================
    # tab:runtime -- timing_120_pairs (1), CNT cell 6 + TM cell 3
    #
    # Added when experiments/runtime_120.py was built as this table's
    # Tier-3 render script (timings themselves are hardware-specific and
    # NOT reproducible across machines -- this Tier-1 check only confirms
    # the archive's OWN cached timings reduce to the paper's macros the way
    # the paper says they do; it says nothing about whether a fresh render
    # on different hardware would match). VacherWSec and GPTsec are NOT
    # checked here: per INVENTORY.md Sec.0 item 7, they come from separate
    # protocols (paper_completion/timing_n20.csv's 20-pair run, and the GPT
    # run report's API latency) that this 120-pair CNT/TM table never
    # covered, even in the source notebooks. DecSecLow (the 128px pass) has
    # no cached file at all (timing_120_ours128.csv is missing from the
    # archive) and is not checked.
    # =====================================================================
    timing_cnt = pd.read_csv(data / "evidence" / "timing_120.csv")
    timing_tm = pd.read_csv(data / "evidence" / "timing_120_tm.csv")
    # abs_tol=0.005 on these two: the paper rounds timings to 2 decimal
    # places (0.09, 0.08), which by itself implies +-0.005 of rounding slack
    # before the underlying median is even compared -- the default 2%-
    # relative tolerance is tighter than that rounding grain alone.
    check("EncodeSec", parse_num(M.get("EncodeSec")), timing_cnt["enc"].median(), source="evidence/timing_120.csv (+recompute, median)", table="tab:runtime", abs_tol=0.005)
    check("DecSec", parse_num(M.get("DecSec")), timing_cnt["dec"].median(), source="evidence/timing_120.csv (+recompute, median)", table="tab:runtime", abs_tol=0.005)
    check("OTTransportSec", parse_num(M.get("OTTransportSec")), timing_cnt["ot"].median(), source="evidence/timing_120.csv (+recompute, median)", table="tab:runtime")
    check("HardAssignSec", parse_num(M.get("HardAssignSec")), timing_cnt["hard"].median(), source="evidence/timing_120.csv (+recompute, median)", table="tab:runtime")
    check("TMEncSec", parse_num(M.get("TMEncSec")), timing_tm["enc"].median(), source="evidence/timing_120_tm.csv (+recompute, median)", table="tab:runtime")
    check("TMInterpSec", parse_num(M.get("TMInterpSec")), timing_tm["gen"].median(), source="evidence/timing_120_tm.csv (+recompute, median; 'gen' column)", table="tab:runtime", abs_tol=0.0006)

    # =====================================================================
    # Write CHECK.md
    # =====================================================================
    df = pd.DataFrame(ROWS)
    matches = (df.status == "MATCH").sum()
    mismatches = (df.status == "MISMATCH").sum()
    no_paper = (df.status == "NO PAPER VALUE").sum()
    no_file = (df.status == "NO FILE ROW").sum()
    info = df.status.str.startswith("SEE NOTE").sum() + df.status.str.startswith("INFO").sum()

    def _display_root(p: Path) -> str:
        # Absolute paths are machine-specific (and can embed the local
        # username) -- report a path relative to this repro package instead
        # of the resolved absolute one, so CHECK.md stays anonymous no
        # matter who generates it or where the archive is unpacked.
        try:
            return str(p.relative_to(PACKAGE_ROOT.parent))
        except ValueError:
            return "(outside the repro package; path omitted for anonymity -- see --data-root/--paper-root)"

    lines = []
    lines.append("# CHECK.md -- score_only.py macro reproduction report\n")
    lines.append(f"Data root: `{_display_root(data)}`\n")
    lines.append(f"Paper root: `{_display_root(paper_root)}`\n")
    lines.append("")
    lines.append(f"**{len(df)} rows checked. {matches} MATCH, {mismatches} MISMATCH, {no_file} have no per-pair file row (see notes per row), {no_paper} have no corresponding paper macro, {info} informational.**\n")
    lines.append("Tolerance: |diff| <= max(0.0006, 2% relative) for plain values (0.0006 covers the")
    lines.append("trace-vs-len KID reference-term offset of ~0.000245); wider tolerances are used")
    lines.append("explicitly for bootstrap CIs and derived percentages, and are noted per row where")
    lines.append("they differ from the default.\n")

    def fmt(v, plus=False):
        if v is None:
            return "\u2014"
        try:
            v = float(v)
        except (TypeError, ValueError):
            return str(v)
        return f"{v:+.6g}" if plus else f"{v:.6g}"

    if mismatches:
        lines.append("## Mismatches\n")
        lines.append("| Table | Macro | Paper | Computed | Diff | Source |")
        lines.append("|---|---|---|---|---|---|")
        for _, row in df[df.status == "MISMATCH"].iterrows():
            lines.append(f"| {row.table} | `{row.macro}` | {fmt(row.paper)} | {fmt(row.computed)} | {fmt(row.delta, plus=True)} | {row.source} |")
        lines.append("")

    lines.append("## All checks, by table\n")
    for table, g in df.groupby("table", sort=False):
        lines.append(f"### {table} ({len(g)} rows)\n")
        lines.append("| Macro | Paper | Computed | Diff | Status | Source |")
        lines.append("|---|---|---|---|---|---|")
        for _, row in g.iterrows():
            lines.append(f"| `{row.macro}` | {fmt(row.paper)} | {fmt(row.computed)} | {fmt(row.delta, plus=True)} | {row.status} | {row.source} |")
        lines.append("")

    lines.append("## Not attempted in this script (see INVENTORY.md §0/§2 for why)\n")
    lines.append("These paper values have no per-pair CSV or raw feature cache in the archive")
    lines.append("(they exist only as notebook-printed output), or require re-deriving the")
    lines.append("Kynkaanniemi manifold-realism radii rather than reading an already-scored")
    lines.append("per-pair value, which risks a false mismatch from RNG differences:\n")
    lines.append("- `tab:app-representation` (n=40 DINO/SAM/CNT feature spread)")
    lines.append("- `tab:app-realism` (n=100 LPIPS-control realism)")
    lines.append("- `tab:app-position` (n=120 self-supervised position estimator)")
    lines.append("- `tab:app-order` and the swap/rerun prose (Vacher rows unverified even against the file)")
    lines.append("- `tab:app-repeat` (repeated-operation degradation, autoencoder row is printed-only)")
    lines.append("- `tab:app-vacher` FID column (printed-only; timing macros ARE checked above)")
    lines.append("- Anchor-mixture prose (`AnchorChangeA/B`), sparse-coding prose, round-trip prose")
    lines.append("- `\\GPTsec`, `\\GPTcostUSD`, `\\GPTOrderRatio*`, `\\GPTPathMono`, `\\GPTPathRtwo` (from the GPT run report, outside this data root)")
    lines.append("- `\\ResampleLPIPS`, `\\GEScrambleDReal` (unverified per INVENTORY.md)")
    lines.append("- Old 1,000-pair observer prose and `tab:app-representation`'s CNT rows (printed-only)")
    lines.append("")

    (out_dir / "CHECK.md").write_text("\n".join(lines))
    print(f"[score_only] wrote {out_dir / 'CHECK.md'}")
    print(f"[score_only] {matches} MATCH / {mismatches} MISMATCH / {len(df)} total")
    if mismatches:
        print("[score_only] MISMATCHES:")
        for _, row in df[df.status == "MISMATCH"].iterrows():
            print(f"  {row.table} {row.macro}: paper={row.paper} computed={row.computed:.6g} delta={row.delta:+.6g}")


if __name__ == "__main__":
    main()
