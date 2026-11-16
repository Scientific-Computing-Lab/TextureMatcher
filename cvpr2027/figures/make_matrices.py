import os
# Distance-matrix figures, drawn from the saved matrices on Drive (tier4_v2, tier5).
# Each row is rank-normalised (the query's ranking of all other images), so one outlier image cannot wash out
# the colour scale and the picture shows what retrieval measures. Dark = close. Titles give leave-one-out 1-NN accuracy from the same matrix.
import glob, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from pathlib import Path
R = Path(os.environ.get("CVPR_OUT", "../evidence"))   # folder holding tier4_v2/ and tier5/ (default: the shipped evidence)
OUT = Path(__file__).parent
plt.rcParams.update({"font.family": "sans-serif", "font.size": 8, "axes.titlesize": 8.5, "pdf.fonttype": 42})
MODELS = ["CNT", "SD-VAE", "DINO-RAE"]; DIST = [("positional", "Positional"), ("gaussian", "Gaussian"), ("ot_div", "OT")]

def sym(M):
    M = np.array(M, float); return np.where(M == 0, M.T, M) if np.allclose(np.tril(M, -1), 0) else M
def nn_acc(M, lab):
    Mi = M + np.diag(np.full(len(M), np.inf)); return 100 * (lab[Mi.argmin(1)] == lab).mean()
def ranks(M):
    # row-wise: for each query (row), the rank of every other image among its candidates (0 = nearest)
    n = len(M); P = np.zeros_like(M)
    for i in range(n):
        o = [j for j in range(n) if j != i]; P[i, o] = np.argsort(np.argsort(M[i, o])) / (n - 2)
    return P

def figure(load, lab, block, name, title):
    fig, axes = plt.subplots(3, 3, figsize=(6.6, 6.9), gridspec_kw=dict(wspace=0.08, hspace=0.28))
    for r, m in enumerate(MODELS):
        for c, (k, kn) in enumerate(DIST):
            M = sym(load(m, k)); ax = axes[r, c]
            im = ax.imshow(ranks(M), cmap="viridis", vmin=0, vmax=1, interpolation="nearest")
            for b in (np.arange(block, len(M), block) - 0.5 if block >= 10 else []):
                ax.axhline(b, color="white", lw=0.25, alpha=0.6); ax.axvline(b, color="white", lw=0.25, alpha=0.6)
            ax.set_xticks([]); ax.set_yticks([])
            ax.set_title(f"{kn}: 1-NN {nn_acc(M, lab):.0f}%", pad=3)
            if c == 0: ax.set_ylabel(m, fontsize=9, weight="bold")
    cb = fig.colorbar(im, ax=axes, shrink=0.5, pad=0.02); cb.set_label("rank among the query's candidates (dark = nearest)")
    fig.suptitle(title, y=0.95, fontsize=9)
    for ext in ("pdf", "png"): fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)

if __name__ == "__main__":
  lab_crops = np.repeat(np.arange(40), 4)
  figure(lambda m, k: np.load(R / f"tier5/crops_{m}_{k}_D.npy"), lab_crops, 4, "matrix_crops",
       "Crop retrieval: 40 DTD images x 4 random crops (chance 1.9%); same-image blocks on the diagonal")
  lab_cls = np.load(R / "tier4_v2/CNT_ot_div_class.npy") if False else np.repeat(np.arange(10), 10)
  def load_cls(m, k):
      return np.load(R / (f"tier4_v2/{m}_ot_div_D.npy" if k == "ot_div" else f"tier4/{m}_{k}_D.npy"))
  figure(load_cls, lab_cls, 10, "matrix_classes",
       "Categories: 10 DTD classes x 10 images (chance 10%); same-class blocks on the diagonal")
  print("done")
