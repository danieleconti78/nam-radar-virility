#!/usr/bin/env python3
"""
satelliti.py — da quali altre pagine compra ads ogni brand.

Molti brand non pubblicano solo dalla pagina ufficiale: usano la pagina del fondatore,
di un creator, di un finto magazine ("Good For You Mag" per Everdrop, "Trucchi di
Pulizia" per Giovasa). Queste ads non escono raccogliendo per page_id, e sono spesso
le piu' spinte.

Per ogni brand del set (cliente compreso) si cerca nella Ad Library il nome e il
dominio del sito, e si tengono le pagine le cui ads portano sullo STESSO dominio.
Il dominio di un brand si legge dalle sue ads nel catalogo, non si indovina.

    ~/tools/Scrapling/.venv/bin/python tools/satelliti.py --json data/satelliti.json

Il risultato e' una lista da leggere: le pagine nuove vanno aggiunte a mano in
competitors.json, con slug proprio e lo stesso "nome" del brand (cosi' in dashboard si
sommano). Un marketplace (amazon.it) non e' un dominio di brand e viene saltato.
"""
import argparse, json, os, sys, time
from collections import Counter, defaultdict
from urllib.parse import quote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adlib import api_get, load_competitors, CATALOG
from enrich_reach import load_key

GENERICI = {"amazon.it", "amazon.com", "instagram.com", "facebook.com", "fb.me", "fb.com",
            "bit.ly", "linktr.ee", "wa.me", "api.whatsapp.com", "play.google.com",
            "apps.apple.com", "youtube.com", "tiktok.com", "donnad.it", "m.me"}


def dominio(url):
    try:
        d = urlparse(url or "").netloc.lower()
    except ValueError:
        return ""
    return d[4:] if d.startswith("www.") else d


def cerca(query, paese, pagine, key):
    out, cursore = [], None
    for _ in range(pagine):
        q = f"search/ads?query={quote(query)}&country={paese}&status=ACTIVE&media_type=ALL"
        if cursore:
            q += "&cursor=" + quote(cursore)
        d = None
        for t in range(3):
            try:
                d = api_get(q, key)
                break
            except Exception:
                time.sleep(2 + 3 * t)
        if not d:
            break
        res = d.get("searchResults") or d.get("results") or []
        out += res
        cursore = d.get("cursor")
        if not res or not cursore:
            break
        time.sleep(0.3)
    return out


def link_di(n):
    s = n.get("snapshot") or {}
    u = s.get("link_url") or ""
    if not u:
        for c in s.get("cards") or []:
            if c.get("link_url"):
                return c["link_url"]
    return u


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paese", default="IT")
    ap.add_argument("--pagine", type=int, default=2, help="pagine di risultati per ricerca (1 credito l'una)")
    ap.add_argument("--parole", help="file con una parola chiave per riga: raggruppa per dominio di atterraggio")
    ap.add_argument("--json")
    a = ap.parse_args()
    key = load_key()
    if not key:
        sys.exit("serve SCRAPECREATORS_API_KEY")

    cfg = load_competitors()
    cli = cfg.get("cliente") or {}
    noti = {str(c["page_id"]) for c in cfg["competitors"] if c.get("page_id")}
    if cli.get("page_id"):
        noti.add(str(cli["page_id"]))

    # dominio di ogni brand: quello su cui atterra la maggioranza delle sue ads
    per_brand = defaultdict(Counter)
    for line in open(CATALOG):
        r = json.loads(line)
        nome = cli.get("brand") if r.get("competitor_slug") == "_cliente" else r["competitor"]
        d = dominio(r.get("landing_url"))
        if d and d not in GENERICI:
            per_brand[nome][d] += 1

    if a.parole:
        return per_parola(a, key, noti, {dom.most_common(1)[0][0]: nome for nome, dom in per_brand.items()})

    esito = []
    for nome, dom in sorted(per_brand.items()):
        sito = dom.most_common(1)[0][0]
        trovati = defaultdict(lambda: {"ads": 0, "nome": ""})
        radice = sito.split(".")[0]
        for q in dict.fromkeys([nome, radice]):
            for n in cerca(q, a.paese, a.pagine, key):
                if dominio(link_di(n)) != sito:
                    continue
                pid = str(n.get("page_id") or (n.get("snapshot") or {}).get("page_id") or "")
                if not pid or pid in noti:
                    continue
                t = trovati[pid]
                t["ads"] += 1
                t["nome"] = (n.get("snapshot") or {}).get("page_name") or n.get("page_name") or t["nome"]
        for pid, t in sorted(trovati.items(), key=lambda kv: -kv[1]["ads"]):
            esito.append({"brand": nome, "sito": sito, "page_id": pid, "pagina": t["nome"], "ads_viste": t["ads"]})
        print(f"{nome[:22]:22} {sito:28} {len(trovati)} pagine nuove"
              + "".join(f"\n    + {t['nome'][:34]:34} {pid:17} {t['ads']} ads" for pid, t in trovati.items()),
              flush=True)

    if a.json:
        with open(a.json, "w") as f:
            json.dump(esito, f, ensure_ascii=False, indent=1)
        print(f"\n-> {a.json}")


def per_parola(a, key, noti, siti):
    """
    Le pagine satellite raramente nominano il brand: parlano del problema ("muffa",
    "bucato che puzza"). Quindi si cerca sulle parole del settore e si raggruppa per
    dominio di atterraggio. Escono due cose: pagine nuove dei brand che abbiamo, e
    domini che non conosciamo (brand nuovi da valutare).
    """
    parole = [l.strip() for l in open(a.parole) if l.strip() and not l.startswith("#")]
    per_dom = defaultdict(lambda: defaultdict(lambda: {"ads": 0, "nome": "", "parole": set()}))
    for i, p in enumerate(parole, 1):
        res = cerca(p, a.paese, a.pagine, key)
        print(f"  [{i}/{len(parole)}] {p:32} {len(res)} ads", flush=True)
        for n in res:
            d = dominio(link_di(n))
            pid = str(n.get("page_id") or (n.get("snapshot") or {}).get("page_id") or "")
            if not d or d in GENERICI or not pid:
                continue
            t = per_dom[d][pid]
            t["ads"] += 1
            t["parole"].add(p)
            t["nome"] = (n.get("snapshot") or {}).get("page_name") or n.get("page_name") or t["nome"]

    esito = {"satelliti": [], "domini_nuovi": []}
    print("\nPAGINE NUOVE DI BRAND GIA' NEL SET")
    for d, nome in sorted(siti.items(), key=lambda kv: kv[1]):
        for pid, t in sorted(per_dom.get(d, {}).items(), key=lambda kv: -kv[1]["ads"]):
            if pid in noti:
                continue
            esito["satelliti"].append({"brand": nome, "sito": d, "page_id": pid, "pagina": t["nome"], "ads_viste": t["ads"]})
            print(f"  {nome[:20]:20} + {t['nome'][:34]:34} {pid:17} {t['ads']} ads")
    print("\nDOMINI CHE NON CONOSCIAMO (almeno 3 ads)")
    nuovi = []
    for d, pagine in per_dom.items():
        if d in siti:
            continue
        tot = sum(t["ads"] for t in pagine.values())
        if tot < 3:
            continue
        nuovi.append((tot, d, pagine))
    for tot, d, pagine in sorted(nuovi, key=lambda x: -x[0]):
        parole_d = sorted(set().union(*(t["parole"] for t in pagine.values())))
        esito["domini_nuovi"].append({"sito": d, "ads_viste": tot, "parole": parole_d,
            "pagine": [{"page_id": pid, "pagina": t["nome"], "ads_viste": t["ads"]} for pid, t in pagine.items()]})
        print(f"  {d[:32]:32} {tot:4}  " + ", ".join(f"{t['nome'][:24]} ({pid})" for pid, t in
              sorted(pagine.items(), key=lambda kv: -kv[1]["ads"])[:4]) + f"  | {', '.join(parole_d[:4])}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(esito, f, ensure_ascii=False, indent=1)
        print(f"\n-> {a.json}")


if __name__ == "__main__":
    main()
