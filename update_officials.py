"""Atualiza officials.json: nomes de autoridades usados nas perguntas do teste de cidadania que mudam.

Fontes (todas públicas):
  - Congresso (senadores, deputados, delegados): https://unitedstates.github.io/congress-legislators/legislators-current.json
  - Governadores e os quatro cargos federais (Presidente, Vice, Speaker, Chief Justice): Wikipédia (API oficial)
O USCIS bloqueia leitura automática (403), então a lista oficial do USCIS continua sendo a palavra final e o app avisa isso.

Segurança: se qualquer verificação de sanidade falhar (menos de 50 governadores, menos de 98 senadores etc.),
o script termina com erro e NÃO sobrescreve o officials.json anterior.

Uso:  python update_officials.py [caminho_de_saida]
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = "LibbyCivics/1.0 (study app; https://github.com/)"
OUT = sys.argv[1] if len(sys.argv) > 1 else "officials.json"

STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}
OTHER = {"DC": "District of Columbia", "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands", "AS": "American Samoa", "MP": "Northern Mariana Islands"}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def clean(s):
    s = re.sub(r"<style.*?</style>", "", s, flags=re.S)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"\[[^\]]*\]", "", s)          # notas de rodapé [14]
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def wiki_html(page):
    url = "https://en.wikipedia.org/w/api.php?action=parse&format=json&prop=text&redirects=1&page=" + urllib.parse.quote(page)
    return json.loads(fetch(url))["parse"]["text"]["*"]


def governors():
    h = wiki_html("List of current United States governors")
    for t in re.findall(r"<table.*?</table>", h, re.S):
        rows = re.findall(r"<tr.*?</tr>", t, re.S)
        if len(rows) < 48:
            continue
        out = {}
        for r in rows:
            cells = [clean(c) for c in re.findall(r"<t[hd].*?</t[hd]>", r, re.S)]
            if len(cells) < 3:
                continue
            state = re.sub(r"\s*\(list\)$", "", cells[0])
            if state in STATES.values():
                # a coluna do governador é a primeira com texto depois da imagem
                name = next((c for c in cells[1:] if c and not c.startswith(("Republican", "Democratic", "Independent"))), "")
                out[state] = name
        if len(out) >= 50:
            return out
    raise RuntimeError("tabela de governadores não encontrada")


def incumbent(page):
    h = wiki_html(page)
    # infobox: "Incumbent<br /><a ...>Nome</a>"; plano B: primeira célula depois do rótulo
    m = re.search(r"Incumbent\s*<br\s*/?>\s*<a [^>]*>([^<]+)</a>", h, re.S)
    if m:
        return clean(m.group(1))
    m = re.search(r"Incumbent.{0,600}?</t[dh]>\s*<t[dh][^>]*>(.*?)</t[dh]>", h, re.S)
    if not m:
        raise RuntimeError("incumbent nao encontrado em " + page)
    return re.split(r"since|Assumed|\.mw-parser", clean(m.group(1)))[0].strip()


def congress():
    data = json.loads(fetch("https://unitedstates.github.io/congress-legislators/legislators-current.json"))
    states = {n: {"senators": [], "representatives": []} for n in STATES.values()}
    others = {n: {"delegate": ""} for n in OTHER.values()}
    for p in data:
        t = p["terms"][-1]
        name = p["name"].get("official_full") or (p["name"].get("first", "") + " " + p["name"].get("last", ""))
        ab = t["state"]
        if ab in STATES:
            st = states[STATES[ab]]
            if t["type"] == "sen":
                st["senators"].append(name)
            else:
                st["representatives"].append({"district": t.get("district", 0), "name": name})
        elif ab in OTHER and t["type"] == "rep":
            others[OTHER[ab]]["delegate"] = name
    for st in states.values():
        st["senators"].sort()
        st["representatives"].sort(key=lambda r: r["district"])
    return states, others


def main():
    gov = governors()
    fed = {
        "president": incumbent("President of the United States"),
        "vice_president": incumbent("Vice President of the United States"),
        "speaker": incumbent("Speaker of the United States House of Representatives"),
        "chief_justice": incumbent("Chief Justice of the United States"),
    }
    states, others = congress()
    # verificações de sanidade: nunca publicar dado quebrado
    problems = []
    if len(gov) < 50 or any(not v for v in gov.values()):
        problems.append("governadores incompletos (%d)" % len(gov))
    if any(not v or len(v) > 60 for v in fed.values()):
        problems.append("cargos federais suspeitos: %r" % fed)
    n_sen = sum(len(s["senators"]) for s in states.values())
    n_rep = sum(len(s["representatives"]) for s in states.values())
    if n_sen < 98:
        problems.append("senadores: %d" % n_sen)
    if n_rep < 420:
        problems.append("deputados: %d" % n_rep)
    if any(len(s["senators"]) not in (1, 2) for s in states.values()):
        problems.append("estado com número estranho de senadores")
    if problems:
        sys.exit("NAO ATUALIZADO: " + "; ".join(problems))
    for name, g in gov.items():
        states[name]["governor"] = g
    result = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {
            "congress": "https://unitedstates.github.io/congress-legislators/",
            "governors_and_federal": "https://en.wikipedia.org/",
            "official_check": "https://www.uscis.gov/citizenship/testupdates",
        },
        "federal": fed,
        "states": states,
        "others": others,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    print("OK", OUT, "| senadores", n_sen, "| deputados", n_rep, "| governadores", len(gov), "|", fed)


if __name__ == "__main__":
    main()
