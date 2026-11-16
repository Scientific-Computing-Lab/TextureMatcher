# Human study: decode the answer codes and compute the numbers reported in the paper (Table 4).
# Each finished session produced one anonymous code (TX2-...). It stores 50 bits: for trials 0-24 the coherence
# answer, then the balance answer (1 = the participant chose option b), plus two bits naming the image set.
# Only the final image set (v2) is analysed; codes from the earlier pilot set (v1) are skipped.
# answer_key.csv says, for every trial, which option was OT and which was positional blending ("natural").
import csv, json, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
REPS = ["CNT", "RAE", "TM", "DM"]


def decode(code):
    _, i, r = code.split("-"); h, ck = r[:-1], r[-1]
    assert len(h) == 13 and sum(int(x, 16) for x in i + h) % 16 == int(ck, 16), f"bad checksum: {code}"
    b = [int(x) for d in h for x in f"{int(d, 16):04b}"]
    return {(0, 0): "v1", (1, 0): "v2"}[tuple(b[50:])], b


def load():
    key = list(csv.DictReader(open(HERE / "answer_key.csv")))
    M = []
    for c in (l.strip() for l in open(HERE / "responses.txt")):
        if not c: continue
        s, b = decode(c)
        if s != "v2": continue
        ot = np.zeros((2, 25), int)
        for t in key:
            n = int(t["trial"])
            for q in (0, 1): ot[q, n] = (t["option_b"] if b[q * 25 + n] else t["option_a"]) == "OT"
        M.append(ot)
    M = np.array(M)                                   # participants x {coherence, balance} x 25 trials; 1 = chose OT
    idx = {r: [int(t["trial"]) for t in key if t["representation"] == r] for r in REPS}
    return M, idx


def boot(M, q, trials, pairs_too, n=20000, seed=0):
    """95% percentile bootstrap of the share choosing OT: resample participants (and, if pairs_too, trials)."""
    rng = np.random.default_rng(seed); P = M.shape[0]; T = np.array(trials); out = []
    for _ in range(n):
        p = rng.integers(0, P, P); tt = T[rng.integers(0, len(T), len(T))] if pairs_too else T
        out.append(M[p][:, q][:, tt].mean())
    return (np.percentile(out, [2.5, 97.5]) * 100).tolist()


def summary():
    M, idx = load(); allT = list(range(25)); res = {"N": int(M.shape[0])}
    for q, name in enumerate(["coherence", "balance"]):
        d = res[name] = {"all": float(M[:, q].mean() * 100),
                         "all_ci_participants": boot(M, q, allT, False),
                         "all_ci_participants_and_pairs": boot(M, q, allT, True)}
        for r in REPS:
            d[r] = float(M[:, q, idx[r]].mean() * 100)
            d[r + "_ci_participants"] = boot(M, q, idx[r], False)
            d[r + "_ci_participants_and_pairs"] = boot(M, q, idx[r], True)
    per = M[:, 0].sum(1)
    res["participants_above_half_on_coherence"] = int((per > 12.5).sum())
    res["min_coherence_screens"] = int(per.min()); res["max_coherence_screens"] = int(per.max())
    res["sign_test_p_two_sided"] = 2 * 0.5 ** int(M.shape[0])
    keep = per < 23                                   # robustness: drop the participants who chose OT on >= 23 of 25
    res["coherence_without_near_all_OT"] = {"dropped": int((~keep).sum()), "share": float(M[keep, 0].mean() * 100),
                                            "ci_participants_and_pairs": boot(M[keep], 0, allT, True)}
    res["same_choice_both_questions"] = float((M[:, 0] == M[:, 1]).mean() * 100)
    res["screens_per_representation"] = {r: len(idx[r]) for r in REPS}
    return res


if __name__ == "__main__":
    json.dump(summary(), sys.stdout, indent=1); print()
