# -*- coding: utf-8 -*-
"""Оцінювання експерименту E1: класифікація вимог PROMISE NFR за допомогою LLM.

Запуск (з папки «Експеримент»):  python scripts/evaluate_e1.py
Читає еталон E1_PROMISE/promise_sample_100_еталон.csv і всі файли відповідей
E1_PROMISE/відповіді/E1_<Модель>_<Промпт>_run<N>.txt; формує
E1_PROMISE/результати_E1.csv і E1_PROMISE/результати_E1.md.
"""
import csv, re, sys, itertools, collections
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "E1_PROMISE"
CLASSES = ["F", "A", "FT", "L", "LF", "MN", "O", "PE", "PO", "SC", "SE", "US"]
LINE = re.compile(r"\b(Q\d{3})\s*[;,:\t|]\s*\**\s*([A-Za-z]{1,2})\b")


def load_gold():
    with open(BASE / "promise_sample_100_еталон.csv", encoding="utf-8-sig") as f:
        return {r["ID"]: r["Class"] for r in csv.DictReader(f, delimiter=";")}


def parse_answer(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    if "=== ВІДПОВІДЬ" in text:
        text = text.split("=== ВІДПОВІДЬ", 1)[1]
    pred = {}
    for qid, cls in LINE.findall(text):
        cls = cls.upper()
        if qid not in pred:          # перша відповідь для ID вважається остаточною
            pred[qid] = cls
    return pred


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def kappa(a, b, ids):
    """Каппа Коена між двома розмітками на спільних ID."""
    ids = [i for i in ids if i in a and i in b]
    n = len(ids)
    if not n:
        return float("nan")
    po = sum(a[i] == b[i] for i in ids) / n
    ca, cb = collections.Counter(a[i] for i in ids), collections.Counter(b[i] for i in ids)
    pe = sum(ca[c] * cb[c] for c in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def evaluate(gold, pred):
    ids = list(gold)
    missing = [i for i in ids if i not in pred]
    invalid = [i for i in ids if i in pred and pred[i] not in CLASSES]
    y = {i: pred.get(i, "-") for i in ids}
    acc = sum(gold[i] == y[i] for i in ids) / len(ids)
    per = {}
    for c in CLASSES:
        if c == "PO":
            continue
        tp = sum(gold[i] == c and y[i] == c for i in ids)
        fp = sum(gold[i] != c and y[i] == c for i in ids)
        fn = sum(gold[i] == c and y[i] != c for i in ids)
        if tp + fn:
            per[c] = prf(tp, fp, fn) + (tp + fn,)
    macro_f1 = sum(v[2] for v in per.values()) / len(per)
    nfr_classes = [c for c in per if c != "F"]
    macro_f1_nfr = sum(per[c][2] for c in nfr_classes) / len(nfr_classes)
    # бінарна задача F / NFR (NFR – позитивний клас)
    is_nfr = lambda c: c in CLASSES and c != "F"
    tp = sum(is_nfr(gold[i]) and is_nfr(y[i]) for i in ids)
    fp = sum(not is_nfr(gold[i]) and is_nfr(y[i]) for i in ids)
    fn = sum(is_nfr(gold[i]) and not is_nfr(y[i]) for i in ids)
    bin_p, bin_r, bin_f = prf(tp, fp, fn)
    bin_acc = sum(is_nfr(gold[i]) == is_nfr(y[i]) for i in ids) / len(ids)
    # точність класифікації NFR лише серед вимог, правильно визнаних NFR
    both = [i for i in ids if is_nfr(gold[i]) and is_nfr(y[i])]
    nfr_sub_acc = sum(gold[i] == y[i] for i in both) / len(both) if both else 0.0
    return dict(n=len(ids), missing=len(missing), invalid=len(invalid), acc=acc,
                macro_f1=macro_f1, macro_f1_nfr=macro_f1_nfr, bin_acc=bin_acc,
                bin_p=bin_p, bin_r=bin_r, bin_f1=bin_f, nfr_sub_acc=nfr_sub_acc, per=per)


def main():
    gold = load_gold()
    runs = {}
    for p in sorted((BASE / "відповіді").glob("E1_*_run*.txt")):
        m = re.match(r"E1_(.+)_(P\d)_run(\d+)\.txt", p.name)
        pred = parse_answer(p)
        if not pred:
            print(f"[пропущено – порожній] {p.name}")
            continue
        runs[(m.group(1), m.group(2), int(m.group(3)))] = pred
    if not runs:
        print("Немає заповнених відповідей.")
        return
    rows = []
    for key, pred in sorted(runs.items()):
        r = evaluate(gold, pred)
        rows.append((key, r))
    with open(BASE / "результати_E1.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Модель", "Промпт", "Прогін", "Пропущено", "Некоректні", "Accuracy",
                    "Macro-F1 (11 класів)", "Macro-F1 NFR", "F/NFR Accuracy", "NFR P", "NFR R", "NFR F1",
                    "Точність підкласу NFR"] + [f"F1 {c}" for c in CLASSES if c != "PO"])
        for (mdl, pr, rn), r in rows:
            w.writerow([mdl, pr, rn, r["missing"], r["invalid"]] +
                       [f"{r[k]:.3f}" for k in ("acc", "macro_f1", "macro_f1_nfr", "bin_acc", "bin_p", "bin_r", "bin_f1", "nfr_sub_acc")] +
                       [f"{r['per'][c][2]:.3f}" if c in r["per"] else "" for c in CLASSES if c != "PO"])
    lines = ["# Результати E1 (PROMISE NFR, n = 100)", "",
             "| Модель | Промпт | Прогін | Acc | Macro-F1 | F/NFR F1 | Підклас NFR | Пропущено |",
             "|---|---|---|---|---|---|---|---|"]
    for (mdl, pr, rn), r in rows:
        lines.append(f"| {mdl} | {pr} | {rn} | {r['acc']:.3f} | {r['macro_f1']:.3f} | {r['bin_f1']:.3f} | {r['nfr_sub_acc']:.3f} | {r['missing']} |")
    # стабільність: каппа між прогонами однієї конфігурації
    lines += ["", "## Стабільність (каппа Коена між прогонами однієї конфігурації)", ""]
    groups = collections.defaultdict(dict)
    for (mdl, pr, rn), pred in runs.items():
        groups[(mdl, pr)][rn] = pred
    for (mdl, pr), d in sorted(groups.items()):
        for a, b in itertools.combinations(sorted(d), 2):
            lines.append(f"- {mdl} {pr}: run{a} vs run{b} – κ = {kappa(d[a], d[b], list(gold)):.3f}")
    (BASE / "результати_E1.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
