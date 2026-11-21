# -*- coding: utf-8 -*-
"""Оцінювання експерименту E2: конвеєр «неформальний опис → вимоги → UML → трасування».

Запуск (з папки «Експеримент»):
    python scripts/evaluate_e2.py --suggest   # створити чернетки відповідностей (mapping_*.json) для ручної перевірки
    python scripts/evaluate_e2.py             # обчислити метрики (структурні + порівняння з еталоном за mapping_*.json)

Структурні метрики (не потребують еталона):
    Cov_S   – частка речень-джерел з вимогами, на які посилається хоча б одна вимога;
    Cov_FR  – частка функціональних вимог, реалізованих хоча б одним варіантом використання;
    Orph_UC, Orph_CL – частка варіантів використання / класів без посилань на вимоги;
    Dangl   – кількість посилань на неіснуючі ідентифікатори;
    PUML_ok – кількість синтаксично коректних діаграм PlantUML (якщо доступні java і plantuml.jar).
Метрики відповідності еталону (потребують mapping_*.json, перевіреного експертом):
    P / R / F1 для вимог, акторів, варіантів використання, класів, трас-зв'язків R→UC і R→CL, дефектів.
    У mapping_*.json значення "NEUTRAL" позначає допустимий додатковий елемент (не влучання і не помилка).
    Еталон версії 1.0: альтернативні типи/класи вимог (type_alt, nfr_class_alt) зараховуються як правильні;
    повнота виявлення дефектів рахується за основними дефектами, точність – за основними й додатковими.
"""
import json, re, sys, csv, difflib, subprocess, shutil, tempfile, os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "E2_Кейс"
GOLD = json.loads((BASE / "еталон" / "еталон_E2.json").read_text(encoding="utf-8"))
ANS = BASE / "відповіді"
PLANTUML_JAR = os.environ.get("PLANTUML_JAR", str(Path(__file__).resolve().parent / "plantuml.jar"))

S_ALL = {f"S{i:02d}" for i in range(1, 30)}
S_REQ = sorted({s for r in GOLD["requirements"] for s in r["source"]})


# ---------- розбір відповідей ----------
def sections(text):
    parts = re.split(r"^===\s*(C1|C2|C3|B0)\b.*?===\s*$", text, flags=re.M)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        body = parts[i + 1].strip()
        if body:
            out[parts[i]] = body
    return out


def _loads(s):
    s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        s2 = re.sub(r",\s*([}\]])", r"\1", s)            # хвостові коми
        s2 = re.sub(r"//[^\n]*", "", s2)                    # коментарі
        return json.loads(s2)


def extract_json(text):
    blocks = re.findall(r"```(?:json|JSON)?\s*\n(\{.*?\})\s*```", text, flags=re.S)
    if not blocks:                                          # пошук першого збалансованого {...}
        start = text.find("{")
        depth = 0
        for k in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[k], 0)
            if depth == 0 and start >= 0:
                blocks = [text[start:k + 1]]
                break
    for b in reversed(blocks):                              # остання версія JSON у відповіді
        try:
            return _loads(b)
        except Exception:
            continue
    return None


def extract_puml(text):
    blocks = re.findall(r"@startuml.*?@enduml", text, flags=re.S)
    return blocks[-2:] if len(blocks) >= 2 else blocks


def puml_ok(code):
    if not (shutil.which("java") and Path(PLANTUML_JAR).exists()):
        return None
    d = tempfile.mkdtemp()
    p = Path(d) / "d.puml"
    p.write_text(code, encoding="utf-8")
    env = dict(os.environ, LANG="C.UTF-8", LC_ALL="C.UTF-8")
    r = subprocess.run(["java", "-Djava.awt.headless=true", "-jar", PLANTUML_JAR, "-checkonly", "-charset", "UTF-8", "d.puml"],
                       cwd=d, capture_output=True, env=env)
    return r.returncode == 0


# ---------- структурні метрики ----------
def ids(lst):
    return {x.get("id") for x in lst or [] if isinstance(x, dict)}


def structural_c1(c1):
    reqs = c1.get("requirements", [])
    srcs = [s for r in reqs for s in r.get("source", [])]
    bad_src = sum(s not in S_ALL for s in srcs)
    cov_s = len(set(srcs) & set(S_REQ)) / len(S_REQ)
    ctx_only = sum(bool(r.get("source")) and set(r["source"]) <= {"S01", "S02"} for r in reqs)
    no_src = sum(not r.get("source") for r in reqs)
    return dict(n_req=len(reqs), n_fr=sum(r.get("type") == "FR" for r in reqs),
                n_nfr=sum(r.get("type") == "NFR" for r in reqs), cov_s=cov_s, bad_src=bad_src,
                ctx_only=ctx_only, no_src=no_src, n_issues=len(c1.get("issues", [])))


def structural_model(m, reqs=None, puml=()):
    uc, cl = m.get("use_cases", []), m.get("classes", [])
    act, asc = m.get("actors", []), m.get("associations", [])
    res = dict(n_actors=len(act), n_uc=len(uc), n_cl=len(cl), n_assoc=len(asc),
               n_gen=len(m.get("generalizations", [])))
    a_ids, c_ids, u_ids = ids(act), ids(cl), ids(uc)
    dangl = sum(a not in a_ids for u in uc for a in u.get("actors", []))
    dangl += sum(x.get("source") not in c_ids or x.get("target") not in c_ids for x in asc)
    dangl += sum(x.get("source") not in u_ids or x.get("target") not in u_ids for x in m.get("uc_relations", []))
    if reqs is not None:
        r_ids = ids(reqs)
        fr = [r["id"] for r in reqs if r.get("type") == "FR"]
        realized = {x for u in uc for x in u.get("realizes", [])}
        res["cov_fr"] = sum(f in realized for f in fr) / len(fr) if fr else 0.0
        res["orph_uc"] = sum(not u.get("realizes") for u in uc) / len(uc) if uc else 0.0
        res["orph_cl"] = sum(not c.get("realizes") for c in cl) / len(cl) if cl else 0.0
        dangl += sum(x not in r_ids for e in uc + cl for x in e.get("realizes", []))
    res["dangl"] = dangl
    checks = [puml_ok(p) for p in puml]
    res["puml_n"] = len(puml)
    res["puml_ok"] = None if any(c is None for c in checks) else sum(checks)
    if puml:
        squash = lambda z: re.sub(r"\\n|\s", "", z or "")   # ігнорувати переноси \n і пробіли в підписах
        txt = squash("\n".join(puml))
        names = [squash(e.get("name", "")) for e in uc + cl + act]
        res["json_puml_agree"] = sum(bool(n) and n in txt for n in names) / len(names) if names else 0.0
    return res


# ---------- відповідність еталону ----------
def norm(s):
    return re.sub(r"[^0-9a-zа-яіїєґ']", "", (s or "").lower())


def sim(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def suggest_names(llm, gold, thr=0.62):
    out = {}
    for e in llm:
        best = max(gold, key=lambda g: sim(e.get("name"), g["name"]))
        out[e.get("id")] = best["id"] if sim(e.get("name"), best["name"]) >= thr else None
    return out


def suggest_reqs(llm_reqs, thr=0.35):
    out = {}
    for r in llm_reqs:
        def score(g):
            a, b = set(r.get("source", [])), set(g["source"])
            jac = len(a & b) / len(a | b) if a | b else 0
            return 0.6 * jac + 0.4 * sim(r.get("text"), g["text"])
        best = max(GOLD["requirements"], key=score)
        out[r.get("id")] = best["id"] if score(best) >= thr else None
    return out


def suggest_issues(llm_issues):
    out = {}
    for i in llm_issues:
        a = set(i.get("source", []))
        cand = [g for g in GOLD["issues"] if a & set(g["source"])]
        # перевага – основним дефектам, далі – з тим самим типом і більшим перетином джерел
        cand.sort(key=lambda g: (g.get("level", "основний") != "основний", g["type"] != i.get("type"), -len(a & set(g["source"]))))
        out[i.get("id")] = cand[0]["id"] if cand else None
    return out


NEUTRAL = "NEUTRAL"   # допустимий додатковий елемент: не враховується ні як влучання, ні як помилка


def prf_map(mapping, n_llm, gold_total):
    n_llm -= sum(v == NEUTRAL for v in mapping.values())
    matched = [v for v in mapping.values() if v and v != NEUTRAL]
    p = len(matched) / n_llm if n_llm else 0.0
    r = len(set(matched)) / gold_total if gold_total else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def prf_sets(pred, gold):
    tp = len(pred & gold)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gold) if gold else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def gold_links(kind):
    key = "use_cases" if kind == "UC" else "classes"
    return {(x, e["id"]) for e in GOLD[key] for x in e["realizes"]}


def compare(stage, data, mp, reqmap):
    res = {}
    if stage == "C1":
        m = mp["requirements"]
        res["req_P"], res["req_R"], res["req_F1"] = prf_map(m, len(data.get("requirements", [])), len(GOLD["requirements"]))
        g = {r["id"]: r for r in GOLD["requirements"]}
        pairs = [(r, g[m[r["id"]]]) for r in data.get("requirements", []) if m.get(r.get("id"))]
        ok_type = lambda r, gr: r.get("type") in [gr["type"]] + gr.get("type_alt", [])
        res["type_acc"] = sum(ok_type(r, gr) for r, gr in pairs) / len(pairs) if pairs else 0.0
        nfr = [(r, gr) for r, gr in pairs if gr["type"] == "NFR" and r.get("type") == "NFR"]
        ok_cls = lambda r, gr: r.get("nfr_class") in [gr["nfr_class"]] + gr.get("nfr_class_alt", [])
        res["nfr_class_acc"] = sum(ok_cls(r, gr) for r, gr in nfr) / len(nfr) if nfr else 0.0
        # дефекти: точність – за всіма еталонними (основні + додаткові), повнота – лише за основними
        mi = mp.get("issues", {})
        core = {i["id"] for i in GOLD["issues"] if i.get("level", "основний") == "основний"}
        n_llm = len(data.get("issues", []))
        n_llm -= sum(v == NEUTRAL for v in mi.values())
        matched = [v for v in mi.values() if v and v != NEUTRAL]
        p = len(matched) / n_llm if n_llm else 0.0
        r = len(set(matched) & core) / len(core) if core else 0.0
        res["iss_P"], res["iss_R"], res["iss_F1"] = p, r, (2 * p * r / (p + r) if p + r else 0.0)
        res["iss_core_found"] = f"{len(set(matched) & core)} з {len(core)}"
        return res
    for key, gk, tag in (("actors", "actors", "act"), ("use_cases", "use_cases", "uc"), ("classes", "classes", "cl")):
        m = mp.get(key, {})
        res[f"{tag}_P"], res[f"{tag}_R"], res[f"{tag}_F1"] = prf_map(m, len(data.get(key, [])), len(GOLD[gk]))
    if stage in ("C2", "C3") and reqmap:
        for key, kind in (("use_cases", "UC"), ("classes", "CL")):
            em = mp.get(key, {})
            pred = {(reqmap.get(x), em.get(e.get("id"))) for e in data.get(key, []) for x in e.get("realizes", [])}
            pred = {p for p in pred if p[0] and p[1] and NEUTRAL not in p}
            gl = gold_links(kind)
            if kind == "UC":
                gl = {l for l in gl if l[0].startswith("FR")}
                pred = {p for p in pred if p[0].startswith("FR")}
            res[f"tr_{kind}_P"], res[f"tr_{kind}_R"], res[f"tr_{kind}_F1"] = prf_sets(pred, gl)
    return res


# ---------- основна процедура ----------
def run(suggest=False):
    rows = []
    for f in sorted(ANS.glob("E2_*_run*.txt")):
        secs = sections(f.read_text(encoding="utf-8", errors="replace"))
        if not secs:
            print(f"[пропущено – порожній] {f.name}")
            continue
        parsed = {k: (extract_json(v), extract_puml(v)) for k, v in secs.items()}
        mpath = ANS / f"mapping_{f.stem}.json"
        if suggest:
            mp = {}
            if parsed.get("C1", (None,))[0]:
                c1 = parsed["C1"][0]
                mp["C1"] = dict(requirements=suggest_reqs(c1.get("requirements", [])), issues=suggest_issues(c1.get("issues", [])))
            for st in ("C2", "C3", "B0"):
                if parsed.get(st, (None,))[0]:
                    d = parsed[st][0]
                    mp[st] = {k: suggest_names(d.get(k, []), GOLD[k]) for k in ("actors", "use_cases", "classes")}
            mp["_статус"] = "ЧЕРНЕТКА: автоматичні відповідності; перевірити й виправити вручну (null – немає відповідника)"
            mpath.write_text(json.dumps(mp, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[mapping] {mpath.name}")
            continue
        mp = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
        c1 = parsed.get("C1", (None, []))[0]
        reqs = c1.get("requirements", []) if c1 else None
        reqmap = mp.get("C1", {}).get("requirements")
        for st, (data, puml) in parsed.items():
            if data is None:
                rows.append(dict(file=f.stem, stage=st, error="JSON не розпізнано"))
                continue
            r = dict(file=f.stem, stage=st)
            r.update(structural_c1(data) if st == "C1" else structural_model(data, reqs if st in ("C2", "C3") else None, puml))
            if st in mp:
                r.update(compare(st, data, mp[st], reqmap))
            rows.append(r)
    if suggest or not rows:
        return
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(BASE / "результати_E2.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.3f}" if isinstance(v, float) else v) for k, v in r.items()})
    for r in rows:
        print(r)


if __name__ == "__main__":
    run(suggest="--suggest" in sys.argv)
