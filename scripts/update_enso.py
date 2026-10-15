#!/usr/bin/env python3
"""Atualiza data/enso.json com os dados mais recentes do CPC/NOAA.

Roda no GitHub Actions (veja .github/workflows/atualizar-dados.yml), mas também
funciona no seu computador:  python scripts/update_enso.py

Usa só a biblioteca padrão do Python. Se uma fonte falhar, os valores anteriores
do arquivo são mantidos, para a página nunca ficar sem dados.
"""
import html as htmllib
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "enso.json"

# Fontes (se a NOAA mudar algum endereço, ajuste aqui)
WEEKLY_URL = "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"
RONI_URLS = [
    "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt",
]
DISCUSSION_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"
SOI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/soi"
HEAT_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ocean/index/heat_content_index.txt"
MONTHS_KEEP = 48  # meses guardados para os gráficos de SOI e calor do oceano

MESES_EN = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
SEASONS = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "monitor-el-nino/1.0 (GitHub Actions)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def pt_date(day: int, month: int, year: int) -> str:
    return f"{day} {MESES_PT[month - 1]} {year}"


def parse_weekly(text: str, weeks: int = 12) -> dict:
    """wksst9120.for: data + (TSM, anomalia) para Niño 1+2, 3, 3.4 e 4."""
    rows = []
    for line in text.splitlines():
        m = re.match(r"\s*(\d{2})([A-Z]{3})(\d{4})\s+(.*)", line)
        if not m:
            continue
        nums = re.findall(r"-?\d+\.\d", m.group(4))
        if len(nums) < 8:
            continue
        d, mon, y = int(m.group(1)), MESES_EN[m.group(2)], int(m.group(3))
        anom = [float(nums[i]) for i in (1, 3, 5, 7)]
        rows.append(((y, mon, d), anom))
    if not rows:
        raise ValueError("nenhuma linha semanal reconhecida")
    rows = rows[-weeks:]
    keys = ["n12", "n3", "n34", "n4"]
    out = {}
    for k_i, k in enumerate(keys):
        series = [r[1][k_i] for r in rows]
        prev = series[-5] if len(series) >= 5 else series[0]
        out[k] = {"week": series[-1], "prev": prev, "series": series}
    (y, mon, d) = rows[-1][0]
    return {"regions": out, "weekLabel": "semana centrada em " + pt_date(d, mon, y),
            "prevLabel": "há 4 semanas"}


def parse_roni(text: str) -> dict:
    """Tabela sazonal: linhas com 'DJF 1950 ... -1.5' (o último número é a anomalia)."""
    vals = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0] not in SEASONS:
            continue
        try:
            year = int(parts[1])
            anom = float(parts[-1])
        except ValueError:
            continue
        vals[(year, SEASONS.index(parts[0]))] = anom
    if not vals:
        raise ValueError("nenhuma linha do RONI reconhecida")
    start = min(k[0] for k in vals)
    last = max(vals)
    seq = []
    y, s = start, 0
    while (y, s) <= last:
        if (y, s) not in vals:
            raise ValueError(f"lacuna no RONI em {SEASONS[s]} {y}")
        seq.append(round(vals[(y, s)], 2))
        s += 1
        if s == 12:
            y, s = y + 1, 0
    return {"start": start, "values": seq}


def parse_discussion(html: str) -> dict:
    text = re.sub(r"<[^>]+>", " ", html)
    text = htmllib.unescape(text).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    out = {}
    m = re.search(r"ENSO Alert System Status:\s*(.+?)\s*Synopsis:", text)
    if m:
        out["status"] = m.group(1).strip()
    m = re.search(r"Synopsis:\s*(.+?\.)\s", text)
    if m:
        out["synopsis"] = m.group(1).strip()
    m = re.search(r"NCEP/NWS\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if m:
        out["discussionDate"] = en_date(m.group(1), m.group(2), m.group(3))
    m = re.search(r"next ENSO Diagnostics? Discussion is scheduled for\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if m:
        out["nextUpdate"] = en_date(m.group(1), m.group(2), m.group(3))
    return out


def monthly_series(pairs: list) -> dict:
    """[((ano, mês), valor), ...] em ordem -> {"start": "AAAA-MM", "values": [...]} dos últimos meses."""
    pairs = pairs[-MONTHS_KEEP:]
    if not pairs:
        raise ValueError("série vazia")
    (y, m), _ = pairs[0]
    return {"start": f"{y}-{m:02d}", "values": [v for _, v in pairs]}


def parse_soi(text: str) -> dict:
    """Arquivo 'soi' do CPC: usa a segunda tabela (STANDARDIZED DATA), ano + 12 meses.
    Os números às vezes vêm colados ('-2.0-999.9'), por isso a leitura é por regex."""
    part = text.split("STANDARDIZED", 1)
    if len(part) < 2:
        raise ValueError("tabela padronizada do SOI não encontrada")
    pairs = []
    for line in part[1].splitlines():
        m = re.match(r"\s*(\d{4})(.*)", line)
        if not m:
            continue
        vals = re.findall(r"-?\d+\.\d", m.group(2))
        if len(vals) != 12:
            continue
        for mon, v in enumerate(vals, 1):
            f = float(v)
            if f > -99:
                pairs.append(((int(m.group(1)), mon), f))
    return monthly_series(pairs)


def parse_heat(text: str) -> dict:
    """heat_content_index.txt: ano, mês e anomalia média dos 300 m superiores (usa 160E-80W)."""
    pairs = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        try:
            pairs.append(((int(parts[0]), int(parts[1])), round(float(parts[3]), 2)))
        except ValueError:
            continue
    return monthly_series(pairs)


def en_date(d, month_name, y) -> str:
    mon = MESES_EN.get(month_name[:3].upper())
    return pt_date(int(d), mon, int(y)) if mon else f"{d} {month_name} {y}"


def main() -> int:
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    ok = []

    try:
        w = parse_weekly(fetch(WEEKLY_URL))
        data["regions"] = w["regions"]
        data["weekLabel"] = w["weekLabel"]
        data["prevLabel"] = w["prevLabel"]
        ok.append("semanal")
    except Exception as e:  # noqa: BLE001
        print(f"[aviso] dados semanais: {e}", file=sys.stderr)

    for url in RONI_URLS:
        try:
            data["roni"] = parse_roni(fetch(url))
            ok.append("RONI")
            break
        except Exception as e:  # noqa: BLE001
            print(f"[aviso] RONI ({url}): {e}", file=sys.stderr)

    try:
        data.update(parse_discussion(fetch(DISCUSSION_URL)))
        ok.append("discussão")
    except Exception as e:  # noqa: BLE001
        print(f"[aviso] discussão mensal: {e}", file=sys.stderr)

    for key, url, parser in (("soi", SOI_URL, parse_soi), ("heat", HEAT_URL, parse_heat)):
        try:
            data[key] = parser(fetch(url))
            ok.append(key)
        except Exception as e:  # noqa: BLE001
            print(f"[aviso] {key}: {e}", file=sys.stderr)

    if not ok:
        print("Nenhuma fonte respondeu; arquivo mantido como estava.", file=sys.stderr)
        return 0

    data["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Atualizado:", ", ".join(ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())
