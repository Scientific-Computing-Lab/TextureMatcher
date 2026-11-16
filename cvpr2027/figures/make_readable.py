# Readable crop-retrieval matrix for the main paper (figures4papers style).
# First 8 of the 40 source images in the saved order (not hand-picked), 4 crops each = 32 rows.
# Colour: for each query row, how close every shown crop is, as a percentile among ALL 159 other crops.
# Dot: the query's nearest neighbour among ALL 160 crops; green = a crop of the same image, red = another image
# (red dots in the right margin = the neighbour is one of the 32 other images not shown).
import json, random, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
from PIL import Image
from pathlib import Path
from make_matrices import R, sym, OUT
import os
DTD = Path(os.environ.get("DTD_DIR", "dtd/images"))   # DTD images folder (dtd/images/<class>/<file>.jpg)
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"], "font.size": 7,
                     "axes.titlesize": 7, "pdf.fonttype": 42, "axes.linewidth": 0.6})
GREEN, RED, BLUE = "#2E8B57", "#B64342", "#0F4D92"
N_IMG, K = 8, 4; n = N_IMG * K
src = json.load(open(R / "tier5/tier5_results.json"))["sources"]
rc = random.Random(2029); thumbs = []
for si, (c, f) in enumerate(src[:N_IMG]):          # reproduce tier5's crops (same seed, same order)
    im = Image.open(DTD / c / f).convert("RGB"); W, H = im.size; s = int(0.6 * min(W, H)); cr = []
    for _ in range(K):
        x0, y0 = rc.randint(0, W - s), rc.randint(0, H - s); cr.append(im.crop((x0, y0, x0 + s, y0 + s)).resize((96, 96), Image.BICUBIC))
    thumbs.append(cr[0])
lab = np.repeat(np.arange(40), K)

def panel(ax, M, title, thumbs_left):
    Mi = M + np.diag(np.full(len(M), np.inf))
    pct = np.zeros((n, n))
    for i in range(n):
        o = np.argsort(np.argsort(np.delete(M[i], i))) / (len(M) - 2); row = np.insert(o, i, np.nan); pct[i] = row[:n]
    ax.imshow(1 - pct, cmap="Blues", vmin=0, vmax=1, interpolation="nearest", extent=(-.5, n - .5, n - .5, -.5))
    for b in range(N_IMG):
        ax.add_patch(Rectangle((b * K - .5, b * K - .5), K, K, fill=False, ec="black", lw=0.7))
    hits = 0
    for i in range(n):
        j = int(Mi[i].argmin()); ok = lab[j] == lab[i]; hits += ok
        x = j if j < n else n + 0.9
        ax.plot(x, i, "o", ms=2.3, mfc=GREEN if ok else RED, mec="white", mew=0.3, clip_on=False, zorder=5)
    ax.set_xlim(-.5, n + 1.6); ax.set_ylim(n - .5, -.5)
    ax.set_xticks([]); ax.set_yticks([]); [sp.set_visible(False) for sp in ax.spines.values()]
    ax.plot([n - .5, n - .5], [-.5, n - .5], color="#999999", lw=0.4)
    ax.set_title(title, pad=7)
    ax.text(n + 0.9, -1.0, "other\ntexture", ha="center", va="bottom", fontsize=4.8, color=RED, linespacing=0.9)
    ax.imshow(np.full((1, 1, 3), 0.85), extent=(-.5, -.5, -.5, -.5))
    ax.text(n / 2, n + 0.6, f"{hits}/{n} found own texture", ha="center", va="top", fontsize=5.6,
            color=GREEN if hits > n / 2 else RED, weight="bold")
    if thumbs_left:
        for b, t in enumerate(thumbs):
            ia = ax.inset_axes([-4.6, b * K - .5 + 0.2, 3.6, K - 0.4], transform=ax.transData); ia.imshow(t); ia.axis("off")

def figure(model, name):
    P = sym(np.load(R / f"tier5/crops_{model}_positional_D.npy")); O = sym(np.load(R / f"tier5/crops_{model}_ot_div_D.npy"))
    fig, axes = plt.subplots(1, 2, figsize=(3.3, 1.95), gridspec_kw=dict(wspace=0.18))
    panel(axes[0], P, "Positional", True); panel(axes[1], O, "OT", False)
    fig.text(0.53, 0.075, "box: 4 crops of one texture  ·  dark: similar  ·  dot: nearest match",
             ha="center", fontsize=5.2, color="#444444")
    for ext in ("pdf", "png"): fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)

for m in ["CNT", "SD-VAE"]: figure(m, f"readable_{m}")
print("ok")
