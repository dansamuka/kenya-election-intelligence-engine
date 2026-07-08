"""
Phase 4B ward-electoral database ingestion.

This module ingests the uploaded Kenya Ward Electoral Database workbook into
machine-readable JSON files used by the regional swing, county threshold, and
constituency proxy models.

Important methodological caveat:
The workbook is highly useful as a voter-geography and registered-voter spine,
but it does not contain ward-level presidential results. The Ruto/Raila 2022
shares are county-level presidential shares applied to all wards in a county.
All regional swing outputs based on these figures are therefore assumption-driven
scenario diagnostics, not forecasts.
"""
from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
WORKBOOK_PATH = DATA_DIR / "source_workbooks" / "Kenya_Ward_Electoral_Database_v3_COMPLETE.xlsx"

GEOGRAPHY_DIR = DATA_DIR / "geography"
ELECTIONS_DIR = DATA_DIR / "elections"
MODEL_DIR = DATA_DIR / "model"
FOUNDATION_DIR = DATA_DIR / "foundation"
CONSTITUENCY_DIR = DATA_DIR / "constituency"

OUT_WARDS = GEOGRAPHY_DIR / "wards.json"
OUT_COUNTIES = GEOGRAPHY_DIR / "counties.json"
OUT_CONSTITUENCIES = GEOGRAPHY_DIR / "constituencies.json"
OUT_REGIONAL_CLUSTERS = MODEL_DIR / "regional_clusters.json"
OUT_REGIONAL_ASSUMPTIONS = MODEL_DIR / "regional_swing_assumptions.json"
OUT_WARD_BASELINE = ELECTIONS_DIR / "ward_voter_baseline_2022.json"
OUT_COUNTY_PRESIDENTIAL = ELECTIONS_DIR / "county_presidential_baseline_2022.json"
OUT_WARD_QUALITY = ELECTIONS_DIR / "ward_data_quality_report.json"
OUT_FOUNDATION_GEOGRAPHIES = FOUNDATION_DIR / "geographies.json"
OUT_MANIFEST = GEOGRAPHY_DIR / "manifest.json"

NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def column_index(cell_ref: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_ref).group(1)  # type: ignore[union-attr]
    idx = 0
    for char in letters:
        idx = idx * 26 + (ord(char) - ord("A") + 1)
    return idx - 1


def coerce_value(value: Optional[str], cell_type: Optional[str]) -> Any:
    if value is None:
        return None
    if cell_type == "str":
        return value
    cleaned = value.strip()
    if cleaned == "":
        return None
    try:
        if "." in cleaned or "e" in cleaned.lower():
            return float(cleaned)
        return int(cleaned)
    except ValueError:
        return cleaned


def inline_text(cell: ET.Element) -> Optional[str]:
    texts = []
    for node in cell.findall(".//main:t", NS):
        if node.text is not None:
            texts.append(node.text)
    return "".join(texts) if texts else None


def workbook_sheet_map(zf: zipfile.ZipFile) -> Dict[str, str]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("rel:Relationship", REL_NS)
    }
    out = {}
    for sheet in workbook.findall(".//main:sheet", NS):
        name = sheet.attrib["name"]
        rid = sheet.attrib[f"{{{OFFICE_REL}}}id"]
        target = rel_map[rid].lstrip("/")
        if target.startswith("xl/"):
            out[name] = target
        else:
            out[name] = "xl/" + target
    return out


def parse_sheet(zf: zipfile.ZipFile, sheet_path: str) -> List[List[Any]]:
    root = ET.fromstring(zf.read(sheet_path))
    rows: List[List[Any]] = []
    for row in root.findall(".//main:sheetData/main:row", NS):
        row_values: List[Any] = []
        for cell in row.findall("main:c", NS):
            ref = cell.attrib.get("r", "A1")
            col = column_index(ref)
            while len(row_values) <= col:
                row_values.append(None)
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                value = inline_text(cell)
            else:
                v = cell.find("main:v", NS)
                value = coerce_value(v.text if v is not None else None, cell_type)
            row_values[col] = value
        rows.append(row_values)
    return rows


def load_workbook_tables(path: Path) -> Dict[str, List[List[Any]]]:
    if not path.exists():
        raise FileNotFoundError(f"Ward electoral workbook not found: {path}")
    with zipfile.ZipFile(path) as zf:
        mapping = workbook_sheet_map(zf)
        return {name: parse_sheet(zf, sheet_path) for name, sheet_path in mapping.items()}


def as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pct_to_percent(value: Any) -> Optional[float]:
    v = as_float(value)
    if v is None:
        return None
    if 0 <= v <= 1:
        return round(v * 100, 3)
    return round(v, 3)


def safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def parse_ward_database(rows: List[List[Any]]) -> List[Dict[str, Any]]:
    wards = []
    # Row 1 is title, row 2 headers, data starts at row 3.
    for row in rows[2:]:
        if len(row) < 17 or not row[0]:
            continue
        wards.append(
            {
                "ward_id": safe_str(row[0]),
                "county_code": as_int(row[1]),
                "county": safe_str(row[2]),
                "constituency_code": as_int(row[3]),
                "constituency": safe_str(row[4]),
                "ward": safe_str(row[5]),
                "cluster": safe_str(row[6]),
                "registered_voters_2022": as_int(row[7]),
                "registered_voters_2027_projected": as_int(row[8]),
                "turnout_2027_assumption": pct_to_percent(row[9]),
                "projected_votes_2027": as_int(row[10]),
                "ruto_2022_county_share": pct_to_percent(row[11]),
                "raila_2022_county_share": pct_to_percent(row[12]),
                "strategic_alliance_2027_input": pct_to_percent(row[13]),
                "incumbent_2027_input": pct_to_percent(row[14]),
                "data_quality": safe_str(row[15]),
                "source": safe_str(row[16]),
                "methodological_warning": "2022 candidate shares are county-level presidential shares applied to wards; not ward-level presidential results.",
            }
        )
    return wards


def parse_scenario_inputs(rows: List[List[Any]]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    cluster_turnout: Dict[str, float] = {}
    swing_params: Dict[str, float] = {}
    sensitivity: Dict[str, float] = {}
    section = None
    for row in rows:
        label = safe_str(row[0] if len(row) > 0 else None)
        value = row[1] if len(row) > 1 else None
        if not label:
            continue
        label_clean = label.lower()
        if "simulation parameters" in label_clean:
            section = "simulation"
            continue
        if "cluster turnout" in label_clean:
            section = "turnout"
            continue
        if "swing parameters" in label_clean:
            section = "swing"
            continue
        if "alliance cohesion" in label_clean:
            section = "sensitivity"
            continue
        if label.startswith("⚙") or label.startswith("KEY"):
            continue
        v = as_float(value)
        if v is None:
            continue
        if section == "turnout":
            cluster_turnout[label] = round(v * 100 if v <= 1 else v, 3)
        elif section == "swing":
            swing_params[label] = round(v * 100 if abs(v) <= 1 else v, 3)
        elif section == "sensitivity":
            sensitivity[label] = round(v * 100 if v <= 1 else v, 3)
        else:
            params[label] = v
    return {
        "generated_at": utc_now_iso(),
        "source": "Scenario Inputs sheet in Kenya_Ward_Electoral_Database_v3_COMPLETE.xlsx",
        "model_use": "assumption layer for regional swing scenario analysis; not observed results",
        "simulation_parameters": params,
        "cluster_turnout_rates_percent": cluster_turnout,
        "swing_parameters_percent_points_or_floors": swing_params,
        "alliance_cohesion_sensitivity_percent": sensitivity,
    }


def group_counties(wards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    acc: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for w in wards:
        key = (w["county_code"], w["county"])
        rec = acc.setdefault(
            key,
            {
                "level": "county",
                "county_code": w["county_code"],
                "county": w["county"],
                "clusters": defaultdict(int),
                "wards": 0,
                "constituencies": set(),
                "registered_voters_2022": 0,
                "registered_voters_2027_projected": 0,
                "projected_votes_2027": 0,
                "ruto_vote_proxy": 0.0,
                "raila_vote_proxy": 0.0,
                "quality_counts": defaultdict(int),
            },
        )
        rv22 = w.get("registered_voters_2022") or 0
        pv27 = w.get("projected_votes_2027") or 0
        ruto = (w.get("ruto_2022_county_share") or 0) / 100
        raila = (w.get("raila_2022_county_share") or 0) / 100
        rec["wards"] += 1
        rec["constituencies"].add(w.get("constituency"))
        rec["registered_voters_2022"] += rv22
        rec["registered_voters_2027_projected"] += w.get("registered_voters_2027_projected") or 0
        rec["projected_votes_2027"] += pv27
        rec["ruto_vote_proxy"] += pv27 * ruto
        rec["raila_vote_proxy"] += pv27 * raila
        rec["clusters"][w.get("cluster") or "Unknown"] += 1
        rec["quality_counts"][w.get("data_quality") or "Unknown"] += 1
    out = []
    for rec in acc.values():
        total = rec["projected_votes_2027"] or 1
        clusters = dict(rec.pop("clusters"))
        quality = dict(rec.pop("quality_counts"))
        consts = rec.pop("constituencies")
        rec["constituencies"] = len([x for x in consts if x])
        rec["dominant_cluster"] = max(clusters.items(), key=lambda kv: kv[1])[0] if clusters else None
        rec["cluster_counts"] = clusters
        rec["data_quality_counts"] = quality
        rec["ruto_2022_projected_vote_share_percent"] = round(rec.pop("ruto_vote_proxy") * 100 / total, 3)
        rec["raila_2022_projected_vote_share_percent"] = round(rec.pop("raila_vote_proxy") * 100 / total, 3)
        rec["share_source_warning"] = "County-level 2022 presidential shares distributed to wards; not ward-result data."
        out.append(rec)
    return sorted(out, key=lambda x: x["county_code"])


def group_constituencies(wards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    acc: Dict[Tuple[int, str, str], Dict[str, Any]] = {}
    for w in wards:
        key = (w["constituency_code"], w["county"], w["constituency"])
        rec = acc.setdefault(
            key,
            {
                "level": "constituency",
                "constituency_code": w["constituency_code"],
                "constituency": w["constituency"],
                "county_code": w["county_code"],
                "county": w["county"],
                "clusters": defaultdict(int),
                "wards": 0,
                "registered_voters_2022": 0,
                "registered_voters_2027_projected": 0,
                "projected_votes_2027": 0,
                "ruto_vote_proxy": 0.0,
                "raila_vote_proxy": 0.0,
                "quality_counts": defaultdict(int),
            },
        )
        pv27 = w.get("projected_votes_2027") or 0
        rec["wards"] += 1
        rec["registered_voters_2022"] += w.get("registered_voters_2022") or 0
        rec["registered_voters_2027_projected"] += w.get("registered_voters_2027_projected") or 0
        rec["projected_votes_2027"] += pv27
        rec["ruto_vote_proxy"] += pv27 * ((w.get("ruto_2022_county_share") or 0) / 100)
        rec["raila_vote_proxy"] += pv27 * ((w.get("raila_2022_county_share") or 0) / 100)
        rec["clusters"][w.get("cluster") or "Unknown"] += 1
        rec["quality_counts"][w.get("data_quality") or "Unknown"] += 1
    out = []
    for rec in acc.values():
        total = rec["projected_votes_2027"] or 1
        clusters = dict(rec.pop("clusters"))
        rec["dominant_cluster"] = max(clusters.items(), key=lambda kv: kv[1])[0] if clusters else None
        rec["cluster_counts"] = clusters
        rec["data_quality_counts"] = dict(rec.pop("quality_counts"))
        rec["ruto_2022_projected_vote_share_percent"] = round(rec.pop("ruto_vote_proxy") * 100 / total, 3)
        rec["raila_2022_projected_vote_share_percent"] = round(rec.pop("raila_vote_proxy") * 100 / total, 3)
        rec["share_source_warning"] = "County-level presidential baseline applied within constituency. Use as provisional proxy only."
        out.append(rec)
    return sorted(out, key=lambda x: (x["county_code"], x["constituency_code"] or 0, x["constituency"] or ""))


def group_clusters(wards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    acc: Dict[str, Dict[str, Any]] = {}
    for w in wards:
        cluster = w.get("cluster") or "Unknown"
        rec = acc.setdefault(
            cluster,
            {
                "cluster": cluster,
                "wards": 0,
                "counties": set(),
                "constituencies": set(),
                "registered_voters_2022": 0,
                "registered_voters_2027_projected": 0,
                "projected_votes_2027": 0,
                "ruto_vote_proxy": 0.0,
                "raila_vote_proxy": 0.0,
            },
        )
        pv27 = w.get("projected_votes_2027") or 0
        rec["wards"] += 1
        rec["counties"].add(w.get("county"))
        rec["constituencies"].add(w.get("constituency"))
        rec["registered_voters_2022"] += w.get("registered_voters_2022") or 0
        rec["registered_voters_2027_projected"] += w.get("registered_voters_2027_projected") or 0
        rec["projected_votes_2027"] += pv27
        rec["ruto_vote_proxy"] += pv27 * ((w.get("ruto_2022_county_share") or 0) / 100)
        rec["raila_vote_proxy"] += pv27 * ((w.get("raila_2022_county_share") or 0) / 100)
    out = []
    for rec in acc.values():
        total = rec["projected_votes_2027"] or 1
        rec["counties"] = len([x for x in rec["counties"] if x])
        rec["constituencies"] = len([x for x in rec["constituencies"] if x])
        rec["ruto_2022_projected_vote_share_percent"] = round(rec.pop("ruto_vote_proxy") * 100 / total, 3)
        rec["raila_2022_projected_vote_share_percent"] = round(rec.pop("raila_vote_proxy") * 100 / total, 3)
        rec["scenario_role"] = "regional swing cluster used for assumption-driven simulations"
        out.append(rec)
    return sorted(out, key=lambda x: x["cluster"])


def foundation_geographies(counties: List[Dict[str, Any]], constituencies: List[Dict[str, Any]], wards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for c in counties:
        rows.append(
            {
                "level": "county",
                "code": c["county_code"],
                "name": c["county"],
                "parent": "Kenya",
                "registered_voters": c["registered_voters_2022"],
                "projected_votes_2027": c["projected_votes_2027"],
                "cluster": c["dominant_cluster"],
                "source": "Kenya_Ward_Electoral_Database_v3_COMPLETE.xlsx",
                "confidence_note": c["share_source_warning"],
            }
        )
    for c in constituencies:
        rows.append(
            {
                "level": "constituency",
                "code": c["constituency_code"],
                "name": c["constituency"],
                "parent": c["county"],
                "county_code": c["county_code"],
                "registered_voters": c["registered_voters_2022"],
                "projected_votes_2027": c["projected_votes_2027"],
                "cluster": c["dominant_cluster"],
                "source": "Kenya_Ward_Electoral_Database_v3_COMPLETE.xlsx",
                "confidence_note": c["share_source_warning"],
            }
        )
    for w in wards:
        rows.append(
            {
                "level": "ward",
                "code": w["ward_id"],
                "name": w["ward"],
                "parent": w["constituency"],
                "county": w["county"],
                "county_code": w["county_code"],
                "constituency_code": w["constituency_code"],
                "registered_voters": w["registered_voters_2022"],
                "projected_votes_2027": w["projected_votes_2027"],
                "cluster": w["cluster"],
                "source": w["source"],
                "data_quality": w["data_quality"],
                "confidence_note": w["methodological_warning"],
            }
        )
    return rows


def quality_report(wards: List[Dict[str, Any]], counties: List[Dict[str, Any]], constituencies: List[Dict[str, Any]]) -> Dict[str, Any]:
    quality_counts = defaultdict(int)
    source_counts = defaultdict(int)
    rv_total = 0
    proj_total = 0
    for w in wards:
        quality_counts[w.get("data_quality") or "Unknown"] += 1
        source_counts[w.get("source") or "Unknown"] += 1
        rv_total += w.get("registered_voters_2022") or 0
        proj_total += w.get("registered_voters_2027_projected") or 0
    return {
        "generated_at": utc_now_iso(),
        "status": "integrated_with_methodological_caveats",
        "workbook": str(WORKBOOK_PATH.relative_to(ROOT_DIR)),
        "ward_rows": len(wards),
        "county_rows": len(counties),
        "constituency_rows": len(constituencies),
        "registered_voters_2022_total": rv_total,
        "registered_voters_2027_projected_total": proj_total,
        "data_quality_counts": dict(quality_counts),
        "source_counts": dict(source_counts),
        "major_strengths": [
            "provides a national ward-level electoral geography spine",
            "contains registered-voter counts tied to counties, constituencies and wards",
            "includes projected 2027 voter counts and cluster-specific turnout assumptions",
            "contains data-quality flags separating IEBC PDF, Kenya Gazette and constituency-scaled rows",
        ],
        "major_limitations": [
            "ward-level presidential vote shares are not actual ward results; county-level Ruto/Raila 2022 shares are applied to wards",
            "MP seat projections remain proxy-only until constituency-level MP results and candidate/party data are ingested",
            "MRP-style estimates remain not implemented because demographic poststratification cells and poll crosstabs are missing",
            "cluster and 2027 turnout/swing parameters are scenario assumptions, not observed facts",
        ],
        "recommended_next_sources": [
            "official IEBC 2022 presidential results by constituency or polling station",
            "official IEBC 2022 National Assembly candidate/party results by constituency",
            "KNBS constituency/sub-county demographics for MRP-lite cells",
            "pollster crosstabs by region/age/gender/urban-rural where publicly available",
        ],
    }


def manifest() -> Dict[str, Any]:
    return {
        "phase": "Phase 4B - ward electoral database integration",
        "generated_at": utc_now_iso(),
        "source_workbook": str(WORKBOOK_PATH.relative_to(ROOT_DIR)),
        "files_generated": [
            "data/geography/wards.json",
            "data/geography/counties.json",
            "data/geography/constituencies.json",
            "data/elections/ward_voter_baseline_2022.json",
            "data/elections/county_presidential_baseline_2022.json",
            "data/elections/ward_data_quality_report.json",
            "data/model/regional_clusters.json",
            "data/model/regional_swing_assumptions.json",
            "data/foundation/geographies.json",
        ],
        "scope": "Integrates ward-level voter geography and scenario assumptions from the workbook; does not claim ward-level presidential result precision.",
    }


def main() -> None:
    tables = load_workbook_tables(WORKBOOK_PATH)
    wards = parse_ward_database(tables["Ward Database"])
    scenario_assumptions = parse_scenario_inputs(tables["Scenario Inputs"])
    counties = group_counties(wards)
    constituencies = group_constituencies(wards)
    clusters = group_clusters(wards)
    foundation = foundation_geographies(counties, constituencies, wards)
    q = quality_report(wards, counties, constituencies)

    write_json(OUT_WARDS, wards)
    write_json(OUT_COUNTIES, counties)
    write_json(OUT_CONSTITUENCIES, constituencies)
    write_json(OUT_REGIONAL_CLUSTERS, clusters)
    write_json(OUT_REGIONAL_ASSUMPTIONS, scenario_assumptions)
    write_json(OUT_WARD_BASELINE, wards)
    write_json(OUT_COUNTY_PRESIDENTIAL, counties)
    write_json(OUT_FOUNDATION_GEOGRAPHIES, foundation)
    write_json(OUT_WARD_QUALITY, q)
    write_json(OUT_MANIFEST, manifest())

    print("Phase 4B ward data ingestion complete")
    print(f"Wards: {len(wards)}")
    print(f"Counties: {len(counties)}")
    print(f"Constituencies: {len(constituencies)}")
    print(f"Registered voters 2022 total: {q['registered_voters_2022_total']}")


if __name__ == "__main__":
    main()
