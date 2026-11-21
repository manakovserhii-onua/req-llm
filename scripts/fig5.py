import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
plt.rcParams.update({"font.family": "Liberation Serif", "font.size": 9, "axes.edgecolor": "#888888",
                     "axes.linewidth": 0.6, "xtick.color": "#444444", "ytick.color": "#444444", "hatch.linewidth": 0.6})
C1, C2 = "#2a78d6", "#eb6834"
fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16.5/2.54, 7/2.54), dpi=300, sharey=True)
def bars(ax, groups, a, b, la, lb, title):
    import numpy as np
    x = np.arange(len(groups)); w = 0.36
    r1 = ax.bar(x - w/2 - 0.01, a, w, color=C1, label=la, edgecolor="white", linewidth=0.8)
    r2 = ax.bar(x + w/2 + 0.01, b, w, color=C2, label=lb, edgecolor="white", linewidth=0.8, hatch="////")
    for rs in (r1, r2):
        for r in rs:
            ax.text(r.get_x() + r.get_width()/2, r.get_height() + 0.008, f"{r.get_height():.2f}".replace(".", ","),
                    ha="center", va="bottom", fontsize=8, color="#222222")
    ax.set_xticks(x); ax.set_xticklabels(groups, fontsize=9)
    ax.set_ylim(0, 1.1); ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0]); ax.set_yticklabels(["0", "0,2", "0,4", "0,6", "0,8", "1,0"], fontsize=8)
    ax.yaxis.grid(True, color="#e3e3e3", linewidth=0.6); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.set_title(title, fontsize=9)
    if la: ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=1)
bars(ax1, ["GPT-6", "Sonnet 5.5"], [0.800, 0.865], [0.917, 0.868], "P1 (zero-shot)", "P2 (визначення)", "а) E1: macro-F1")
bars(ax2, ["GPT-6", "Sonnet 5.5"], [0.979, 0.990], [0.933, 0.965], "B0 (одноетапна генерація)", "C2 (поетапний конвеєр)", "б) E2: варіанти використання")
bars(ax3, ["GPT-6", "Sonnet 5.5"], [0.965, 0.963], [0.854, 0.962], None, None, "в) E2: класи")
fig.tight_layout(w_pad=1.5)
fig.savefig("fig5.png", dpi=300)
