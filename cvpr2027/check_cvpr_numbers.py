#!/usr/bin/env python3
"""Recompute the numbers that are new in the CVPR version of the paper from the shipped score files.

Every check reads a file under evidence/ (or the human-study answer codes), rounds it the way the paper prints it,
and compares it with the value printed in the paper. Run from this folder:

    python check_cvpr_numbers.py            # prints a summary and writes CHECK_CVPR.md

KID values are x10^3. "dKID" is the paired change in KID against the named base rule, with a 95% bootstrap interval
over pairs. Bootstrap intervals of the human study are Monte Carlo estimates (20,000 resamples); a bound may differ
from the printed one by one percentage point, which the check reports as MATCH (bootstrap).
"""
import csv, json, sys
from pathlib import Path

HERE = Path(__file__).parent
EV = HERE / "evidence"
sys.path.insert(0, str(HERE / "human_study"))


def rows(f): return list(csv.DictReader(open(EV / f)))


def pick(f, **kw):
    out = [r for r in rows(f) if all(r[k] == v for k, v in kw.items())]
    assert len(out) == 1, (f, kw, len(out)); return out[0]


CHECKS = []   # (where in the paper, what, printed value, recomputed value, decimals, tolerance)


def add(where, what, printed, value, dec=1, tol=0.0):
    CHECKS.append((where, what, printed, value, dec, tol))


# ---------------------------------------------------------------- Table 1: every rule in every model (t = .5)
T1 = "Table 1"
def d128(m, b="field_linear", pre="cnt", col="dKIDx1e3"):
    return float(pick("scores/delta_kid_by_t_128.csv", method=f"{pre}_{m}", base=f"{pre}_{b}", t="0.5")[col])
def k128(m, pre): return float(pick("scores/kid_by_t_128.csv", method=f"{pre}_{m}", t="0.5")["KID"]) * 1e3
for pre, name, vals in [("cnt", "CNT", [29.6, -9.0, -4.6, -10.2, -9.6, +0.7]),
                        ("rae", "DINO-RAE", [10.4, -5.3, -6.4, -5.8, -7.1, -2.0])]:
    sharp = "soft_ot_sharp"
    add(T1, f"{name} positional KID", vals[0], k128("field_linear", pre))
    for rule, v in zip(["target_mean", "gaussian", "soft_ot", sharp, "exact_ot"], vals[1:]):
        add(T1, f"{name} {rule} dKID", v, d128(rule, pre=pre))
tm = {r["rule"]: r for r in rows("tier6/tm_delta_kid.csv") if r["base"] == "lerp"}
add(T1, "Tex. Mixer positional KID", 12.1, float(pick("tier6/tm_kid.csv", rule="lerp")["KIDx1e3"]))
for rule, v in zip(["mean", "gaussian", "ot_r0.03", "ot_r0.003", "hard"], [-3.2, -2.0, -2.8, +2.2, +9.5]):
    add(T1, f"Tex. Mixer {rule} dKID", v, float(tm[rule]["dKIDx1e3"]))
add(T1, "SD-VAE positional KID", 21.4, float(pick("tier1/e2_kid_by_t.csv", method="sdvae_field_linear", t="0.5")["KIDx1e3"]))
for rule, v in zip(["target_mean", "gaussian", "soft_ot", "soft_ot_sharp", "exact_ot"], [-6.7, -20.4, -19.8, -18.9, -18.1]):
    add(T1, f"SD-VAE {rule} dKID", v, float(pick("tier1/e2_delta_kid.csv", method=f"sdvae_{rule}", base="sdvae_field_linear", t="0.5")["dKIDx1e3"]))

# ---------------------------------------------------------------- Hero numbers (Fig. 1 / Sec. 4.2), KID at t = .5
H = "Fig. 1 / Sec. 4.2"
add(H, "CNT positional KID, 1,000 pairs", 30.1, float(pick("tier1/e1_kid.csv", method="field_linear", t="0.5")["KIDx1e3"]))
add(H, "CNT soft OT KID, 1,000 pairs", 20.7, float(pick("tier1/e1_kid.csv", method="soft_ot", t="0.5")["KIDx1e3"]))
add(H, "DINO-RAE positional KID", 10.4, k128("field_linear", "rae"))
add(H, "DINO-RAE sharp OT KID", 3.3, k128("soft_ot_sharp", "rae"))
add(H, "Tex. Mixer positional KID", 12.1, float(pick("tier6/tm_kid.csv", rule="lerp")["KIDx1e3"]))
add(H, "Tex. Mixer soft OT KID", 9.3, float(pick("tier6/tm_kid.csv", rule="ot_r0.03")["KIDx1e3"]))
add(H, "SD-VAE positional KID", 21.4, float(pick("tier1/e2_kid_by_t.csv", method="sdvae_field_linear", t="0.5")["KIDx1e3"]))
add(H, "SD-VAE soft OT KID", 1.6, float(pick("tier1/e2_kid_by_t.csv", method="sdvae_soft_ot", t="0.5")["KIDx1e3"]))
dm = pick("scores/dm_ot_vs_official_128.csv", t="0.5")
add(H, "DiffMorpher official KID", 19.9, float(dm["KID_official"]))
add(H, "DiffMorpher OT-attention KID", 20.3, float(dm["KID_ot"]))

# ---------------------------------------------------------------- Sec. 4.2 / 4.4 intervals
S = "Sec. 4.2 / 4.4"
for m, b, v, lo, hi in [("soft_ot", "field_linear", -10.2, -16.0, -4.5), ("gaussian", "field_linear", -4.6, -11.1, 1.9),
                        ("gaussian", "soft_ot", 5.6, 1.0, 10.3)]:
    r = pick("scores/delta_kid_by_t_128.csv", method=f"cnt_{m}", base=f"cnt_{b}", t="0.5")
    for lab, p, c in [("", v, "dKIDx1e3"), (" CI low", lo, "lo"), (" CI high", hi, "hi")]:
        add(S, f"CNT {m} vs {b}{lab}", p, float(r[c]))
for m, v, lo, hi in [("soft_ot_sharp", -7.1, -10.3, -3.9), ("soft_ot", -5.8, -9.4, -2.1)]:
    r = pick("scores/delta_kid_by_t_128.csv", method=f"rae_{m}", base="rae_field_linear", t="0.5")
    for lab, p, c in [("", v, "dKIDx1e3"), (" CI low", lo, "lo"), (" CI high", hi, "hi")]:
        add(S, f"DINO-RAE {m} vs positional{lab}", p, float(r[c]))
add(S, "DINO-RAE sharp OT gain", 68, (1 - k128("soft_ot_sharp", "rae") / k128("field_linear", "rae")) * 100, 0)
add(S, "SD-VAE soft OT gain", 93,
    (1 - float(pick("tier1/e2_kid_by_t.csv", method="sdvae_soft_ot", t="0.5")["KIDx1e3"]) /
     float(pick("tier1/e2_kid_by_t.csv", method="sdvae_field_linear", t="0.5")["KIDx1e3"])) * 100, 0)
for lab, p, c in [("", 0.4, "dKID_ot_minus_official"), (" CI low", -4.9, "lo"), (" CI high", 5.8, "hi")]:
    add(S, f"DiffMorpher OT attention vs official{lab}", p, float(dm[c]))
r = pick("tier6/tm_delta_kid.csv", rule="ot_r0.03", base="gaussian")
for lab, p, c in [("", -0.9, "dKIDx1e3"), (" CI low", -1.6, "lo"), (" CI high", -0.2, "hi")]:
    add(S, f"Tex. Mixer soft OT vs Gaussian{lab}", p, float(r[c]))
r = pick("tier6/tm_delta_kid.csv", rule="mean", base="lerp")
for lab, p, c in [("", -3.1, "dKIDx1e3"), (" CI low", -4.4, "lo"), (" CI high", -1.8, "hi")]:
    add(S, f"Tex. Mixer target mean vs positional{lab}", p, float(r[c]))

# ---------------------------------------------------------------- Supplement: DiffMorpher, LoRA, reversal, path jump, cross-fade
P = "Supplement"
kf = lambda m, t: float(pick("scores/kid_fid_by_t.csv", method=m, t=t)["KID"]) * 1e3
add(P, "DiffMorpher excess KID at t=.5 (over t=0)", 15.7, kf("diffmorpher", "0.5") - kf("diffmorpher", "0.0"))
add(P, "CNT soft OT excess KID at t=.5 (over t=0)", 12.1, kf("cnt_soft_ot", "0.5") - kf("cnt_soft_ot", "0.0"))
r = pick("scores/delta_kid_by_t.csv", method="diffmorpher", base="cnt_soft_ot", t="0.5")
for lab, p, c in [("", -4.8, "dKID"), (" CI low", -13.4, "lo"), (" CI high", 3.9, "hi")]:
    add(P, f"DiffMorpher vs CNT soft OT{lab}", p, float(r[c]) * 1e3)
for b, v, lo, hi in [("cnt_field_linear", -1.7, -4.2, 0.8), ("cnt_soft_ot", 11.0, 5.7, 16.4)]:
    r = pick("scores/delta_kid_by_t.csv", method="cnt_lora_linear", base=b, t="0.5")
    for lab, p, c in [("", v, "dKID"), (" CI low", lo, "lo"), (" CI high", hi, "hi")]:
        add(P, f"LoRA-tuned decoder vs {b}{lab}", p, float(r[c]) * 1e3)
r = pick("scores/reversed_direction_128.csv", rule="soft_ot")
for lab, p, c in [("", 4.4, "dKID_rev_minus_fwd"), (" CI low", -1.7, "lo"), (" CI high", 10.5, "hi")]:
    add(P, f"Reversed direction, soft OT{lab}", p, float(r[c]))
ps = {r["method"]: r for r in rows("scores/progress_summary.csv")}
add(P, "Largest step share, two-sided soft OT", 0.51, float(ps["cnt_twosided_soft_ot"]["max_jump_share"]), 2)
add(P, "Largest step share, directed soft OT", 0.30, float(ps["cnt_soft_ot"]["max_jump_share"]), 2)
add(P, "Largest step share, two-sided positional", 0.29, float(ps["cnt_twosided_field_linear"]["max_jump_share"]), 2)
xf = {r["op"]: r for r in rows("crossfade/metrics_v2.csv")}
for op, v in [("pixel_xfade", 5.7), ("xfade_recon", 15.4), ("soft_ot_paper", 23.2), ("field_linear", 36.5)]:
    add(P, f"Cross-fade study KID, {op}", v, float(xf[op]["KIDx1e3"]))

# ---------------------------------------------------------------- Distance experiment (Fig. 4, Supp. tab:distance)
DIST = "Fig. 4 / Supp. distance table"
crops = json.load(open(EV / "tier5/tier5_results.json"))["results"]["crops"]      # 40 images x 4 crops
cat = json.load(open(EV / "tier4/tier4_results.json"))["results"]                 # 10 DTD classes x 10 images
cat_ot = json.load(open(EV / "tier4_v2/tier4_results.json"))["results"]           # same images, OT divergence
for model, vals in {"CNT": (31, 77, 71), "SD-VAE": (49, 99, 99), "DINO-RAE": (100, 100, 100)}.items():
    for rule, v in zip(["positional", "gaussian", "ot_div"], vals):
        add(DIST, f"crop test, 1-NN is a crop of the same image, {model} {rule} (%)", v, crops[model][rule]["nn_acc"] * 100, 0)
for model, vals in {"CNT": (18, 27, 24), "SD-VAE": (15, 25, 31), "DINO-RAE": (81, 87, 85)}.items():
    for rule, v, src in zip(["positional", "gaussian", "ot_div"], vals, [cat, cat, cat_ot]):
        add(DIST, f"category test, 1-NN has the same DTD class, {model} {rule} (%)", v, src[model][rule]["nn_acc"] * 100, 0)

# ---------------------------------------------------------------- Human study (Table 4, Supp. G)
HS = "Table 4 / Supp. G"
from analyze_responses import summary
h = summary()
add(HS, "participants", 24, h["N"], 0)
c, b = h["coherence"], h["balance"]
for rep, v, P_, X_ in [("all", 71, (66, 76), (60, 81)), ("CNT", 78, (71, 83), (66, 88)), ("RAE", 71, (66, 77), (50, 88)),
                       ("TM", 68, (60, 76), (44, 89)), ("DM", 56, (44, 67), (33, 78))]:
    add(HS, f"coherence, {rep}", v, c[rep], 0)
    add(HS, f"coherence, {rep}, CI over participants low", P_[0], c[f"{rep}_ci_participants"][0], 0, 1)
    add(HS, f"coherence, {rep}, CI over participants high", P_[1], c[f"{rep}_ci_participants"][1], 0, 1)
    add(HS, f"coherence, {rep}, CI over participants and pairs low", X_[0], c[f"{rep}_ci_participants_and_pairs"][0], 0, 1)
    add(HS, f"coherence, {rep}, CI over participants and pairs high", X_[1], c[f"{rep}_ci_participants_and_pairs"][1], 0, 1)
for rep, v in [("all", 38), ("CNT", 38), ("RAE", 39), ("TM", 35), ("DM", 47)]:
    add(HS, f"even mix, {rep}", v, b[rep], 0)
add(HS, "even mix, CI over participants low", 30, b["all_ci_participants"][0], 0, 1)
add(HS, "even mix, CI over participants high", 48, b["all_ci_participants"][1], 0, 1)
add(HS, "positional judged the even mix", 62, 100 - b["all"], 0)
add(HS, "participants above 50% on coherence", 24, h["participants_above_half_on_coherence"], 0)
add(HS, "fewest coherence screens choosing OT", 14, h["min_coherence_screens"], 0)
ne = h["coherence_without_near_all_OT"]
add(HS, "coherence without the 3 near-all-OT participants", 67, ne["share"], 0)
add(HS, "  same, CI low", 56, ne["ci_participants_and_pairs"][0], 0, 1)
add(HS, "  same, CI high", 78, ne["ci_participants_and_pairs"][1], 0, 1)
add(HS, "same image chosen for both questions (%)", 36, h["same_choice_both_questions"], 0)


# ---------------------------------------------------------------- report
def main():
    out, bad = [], 0
    out.append("# CHECK_CVPR: numbers new in the CVPR version, recomputed from evidence/\n")
    out.append("| Where | Quantity | Paper | Recomputed | Status |\n|---|---|---|---|---|")
    counts = {"MATCH": 0, "MATCH (bootstrap)": 0, "LAST DIGIT": 0, "MISMATCH": 0}
    for where, what, printed, value, dec, tol in CHECKS:
        unit = 10 ** -dec; diff = abs(value - printed)
        if diff <= 0.5 * unit + 1e-9: st = "MATCH"                       # rounds to the printed value (ties either way)
        elif tol and diff <= tol + 0.5 * unit + 1e-9: st = "MATCH (bootstrap)"
        elif diff <= 1.0 * unit + 1e-9: st = "LAST DIGIT"                # printed value is one unit off in its last digit
        else: st = "MISMATCH"
        counts[st] += 1; bad += st == "MISMATCH"
        out.append(f"| {where} | {what} | {printed} | {value:.{dec + 1}f} | {st} |")
    n = len(CHECKS)
    out.insert(1, f"{n} values: " + ", ".join(f"{v} {k}" for k, v in counts.items()) + ".\n\n"
               "MATCH (bootstrap): a human-study interval bound within one point of the printed one (Monte Carlo).\n"
               "LAST DIGIT: the printed value differs by one unit in its last digit (rounding of a two-decimal value).\n")
    (HERE / "CHECK_CVPR.md").write_text("\n".join(out) + "\n")
    print(out[1].splitlines()[0], "Details: CHECK_CVPR.md")
    for line in out:
        if line.startswith("| ") and ("MISMATCH |" in line or "LAST DIGIT" in line or "bootstrap) |" in line): print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
