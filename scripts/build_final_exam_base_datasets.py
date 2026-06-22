from __future__ import annotations

import json
import heapq
import math
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

BOUNDARY_PATHS = {
    "pangyo": RAW_DIR / "pangyo_boundary.geojson",
    "cheongna": RAW_DIR / "cheongna_boundary.geojson",
}

LANDUSE_PATHS = {
    "pangyo": sorted((RAW_DIR / "AL_D154_41_20260412").glob("*.shp")),
    "cheongna": [RAW_DIR / "AL_D154_28_20260412" / "AL_D154_28_20260412.shp"],
}

BUILDING_PATHS = {
    "pangyo": sorted((RAW_DIR / "building").glob("AL_D010_41_20260609*.shp")),
    "cheongna": [RAW_DIR / "building" / "AL_D010_28_20260609.shp"],
}

BUILDING_TABLE_PATHS = {
    "pangyo": RAW_DIR / "building" / "building_pyojebu_bundang.csv",
    "cheongna": RAW_DIR / "building" / "building_pyojebu_seogu.csv",
}

SGIS_SHAPE_PATHS = {
    "pangyo": RAW_DIR / "sgis" / "bnd_oa_31023_2025_2Q" / "bnd_oa_31023_2025_2Q.shp",
    "cheongna": RAW_DIR / "sgis" / "bnd_oa_23080_2025_2Q" / "bnd_oa_23080_2025_2Q.shp",
}

SGIS_POP_PATHS = {
    "pangyo": RAW_DIR / "sgis" / "31023_2023년_인구총괄(총인구).csv",
    "cheongna": RAW_DIR / "sgis" / "23080_2023년_인구총괄(총인구).csv",
}

SGIS_EMP_PATHS = {
    "pangyo": RAW_DIR / "sgis" / "31023_2023년_산업분류별(10차_대분류)_종사자수.csv",
    "cheongna": RAW_DIR / "sgis" / "23080_2023년_산업분류별(10차_대분류)_종사자수.csv",
}

NETWORK_NODES_PATH = RAW_DIR / "subway_network" / "network" / "nodes.tsv"
NETWORK_LINKS_PATH = RAW_DIR / "subway_network" / "network" / "links.tsv"

CORE_STATION_RULES = {
    "pangyo": {"station_name": "판교", "line_names": ["경강선", "신분당선"]},
    "cheongna": {"station_name": "청라국제도시", "line_names": ["공항철도"]},
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def fix_mojibake(value):
    if not isinstance(value, str):
        return value
    try:
        return value.encode("latin1").decode("cp949")
    except Exception:
        return value


def fix_string_columns(frame: pd.DataFrame) -> pd.DataFrame:
    for column in frame.columns:
        if column == "geometry":
            continue
        if frame[column].dtype == object:
            frame[column] = frame[column].map(fix_mojibake)
    return frame


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def normalize_number_str(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = re.sub(r"[^0-9]", "", text)
    return digits


def build_pnu(sigungu_code, legaldong_code, mountain_code, bon, bu) -> str:
    sigungu = normalize_number_str(sigungu_code).zfill(5)
    legaldong = normalize_number_str(legaldong_code).zfill(5)
    mountain = normalize_number_str(mountain_code) or "0"
    mountain = "2" if mountain == "1" else "1"
    bon_code = normalize_number_str(bon).zfill(4)
    bu_code = normalize_number_str(bu).zfill(4)
    return f"{sigungu}{legaldong}{mountain}{bon_code}{bu_code}"


def load_boundary(region: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(BOUNDARY_PATHS[region])
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    gdf["geometry"] = gdf.geometry.make_valid()
    boundary = gdf.dissolve().reset_index(drop=True)
    boundary["region"] = region
    return boundary


def load_network() -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = pd.read_csv(NETWORK_NODES_PATH, sep="\t")
    links = pd.read_csv(NETWORK_LINKS_PATH, sep="\t")
    return nodes, links


def read_shapefile_clipped(path: Path, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    probe = gpd.read_file(path, rows=1)
    target_boundary = boundary.to_crs(probe.crs)
    minx, miny, maxx, maxy = target_boundary.total_bounds
    gdf = gpd.read_file(path, bbox=(minx, miny, maxx, maxy))
    gdf = fix_string_columns(gdf)
    if gdf.empty:
        return gdf
    return gpd.clip(gdf, target_boundary)


def classify_landuse(name: str) -> str:
    text = normalize_text(name)
    patterns = [
        ("주거", ["전용주거지역", "일반주거지역", "준주거지역", "주거지역"]),
        ("상업", ["중심상업지역", "일반상업지역", "근린상업지역", "유통상업지역", "상업지역"]),
        ("공업", ["전용공업지역", "일반공업지역", "준공업지역", "공업지역"]),
        ("녹지", ["보전녹지지역", "생산녹지지역", "자연녹지지역", "녹지지역"]),
        ("관리/보전", ["관리지역", "농림지역", "자연환경보전지역"]),
        ("기반시설", ["도로", "철도", "주차장", "공원", "광장", "하천", "유수지", "학교", "유원지"]),
    ]
    for label, keys in patterns:
        if any(key in text for key in keys):
            return label
    return "기타"


def extract_primary_landuse(raw_names: str) -> str:
    if pd.isna(raw_names):
        return "기타"
    parts = [part.strip() for part in str(raw_names).split(",") if part.strip()]
    for part in parts:
        category = classify_landuse(part)
        if category != "기타":
            return category
    return classify_landuse(parts[0]) if parts else "기타"


def process_landuse(region: str, boundary: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict]:
    frames = []
    for path in LANDUSE_PATHS[region]:
        clipped = read_shapefile_clipped(path, boundary)
        if not clipped.empty:
            frames.append(clipped)
    landuse = pd.concat(frames, ignore_index=True) if frames else gpd.GeoDataFrame(geometry=[], crs=boundary.crs)
    landuse = gpd.GeoDataFrame(landuse, geometry="geometry", crs=frames[0].crs if frames else boundary.crs)
    landuse["designation_names"] = landuse.get("A8", "").map(fix_mojibake).fillna("")
    landuse["primary_landuse"] = landuse["designation_names"].map(extract_primary_landuse)
    landuse["area_m2"] = landuse.geometry.area
    summary = (
        landuse.groupby("primary_landuse", dropna=False)["area_m2"]
        .sum()
        .sort_values(ascending=False)
        .to_dict()
    )
    total_area = sum(summary.values()) or 1.0
    ratio_summary = {key: value / total_area for key, value in summary.items()}
    return landuse[["primary_landuse", "designation_names", "area_m2", "geometry"]], ratio_summary


def classify_building_use(name: str) -> str:
    text = normalize_text(name)
    if any(key in text for key in ["업무시설", "공공업무시설", "오피스텔"]):
        return "업무"
    if any(key in text for key in ["공동주택", "단독주택", "다세대주택", "다가구주택", "기숙사", "주택"]):
        return "주거"
    if any(key in text for key in ["제1종근린생활시설", "제2종근린생활시설", "판매시설", "숙박시설", "위락시설"]):
        return "상업/근생"
    if any(key in text for key in ["교육연구시설", "학교", "연구소"]):
        return "교육연구"
    if any(key in text for key in ["공장", "창고시설", "운수시설"]):
        return "산업/물류"
    return "기타"


def load_building_table(region: str) -> pd.DataFrame:
    table = pd.read_csv(BUILDING_TABLE_PATHS[region], encoding="utf-8-sig")
    table["pnu"] = table.apply(
        lambda row: build_pnu(
            row["시군구코드"],
            row["법정동코드"],
            row["대지구분코드"],
            row["번"],
            row["지"],
        ),
        axis=1,
    )
    table["연면적(㎡)"] = pd.to_numeric(table["연면적(㎡)"], errors="coerce").fillna(0)
    table["건축면적(㎡)"] = pd.to_numeric(table["건축면적(㎡)"], errors="coerce").fillna(0)
    table["대지면적(㎡)"] = pd.to_numeric(table["대지면적(㎡)"], errors="coerce").fillna(0)
    table["용적률(%)"] = pd.to_numeric(table["용적률(%)"], errors="coerce").fillna(0)
    table["building_use_group"] = table["주용도코드명"].map(classify_building_use)
    return table


def process_buildings(region: str, boundary: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict]:
    frames = []
    for path in BUILDING_PATHS[region]:
        clipped = read_shapefile_clipped(path, boundary)
        if not clipped.empty:
            frames.append(clipped)

    buildings = pd.concat(frames, ignore_index=True) if frames else gpd.GeoDataFrame(geometry=[], crs=boundary.crs)
    buildings = gpd.GeoDataFrame(buildings, geometry="geometry", crs=frames[0].crs if frames else boundary.crs)
    buildings["pnu"] = buildings["A2"].astype(str)
    parcels = buildings.dissolve(by="pnu").reset_index()

    table = load_building_table(region)
    grouped = (
        table.groupby(["pnu", "building_use_group"], dropna=False)["연면적(㎡)"]
        .sum()
        .reset_index()
    )
    dominant = grouped.sort_values(["pnu", "연면적(㎡)"], ascending=[True, False]).drop_duplicates("pnu")
    parcel_stats = (
        table.groupby("pnu", dropna=False)
        .agg(
            gross_floor_area_m2=("연면적(㎡)", "sum"),
            building_area_m2=("건축면적(㎡)", "sum"),
            site_area_m2=("대지면적(㎡)", "sum"),
            floor_area_ratio_pct=("용적률(%)", "max"),
        )
        .reset_index()
    )
    parcel_stats = parcel_stats.merge(
        dominant[["pnu", "building_use_group", "연면적(㎡)"]].rename(columns={"연면적(㎡)": "dominant_use_area_m2"}),
        on="pnu",
        how="left",
    )
    parcel_stats["development_intensity"] = parcel_stats.apply(
        lambda row: row["gross_floor_area_m2"] / row["site_area_m2"] if row["site_area_m2"] else math.nan,
        axis=1,
    )

    parcel_gdf = parcels.merge(parcel_stats, on="pnu", how="left")
    summary_area = (
        table.groupby("building_use_group", dropna=False)["연면적(㎡)"]
        .sum()
        .sort_values(ascending=False)
        .to_dict()
    )
    total_area = sum(summary_area.values()) or 1.0
    ratio_summary = {key: value / total_area for key, value in summary_area.items()}
    return parcel_gdf, ratio_summary


def load_sgis_metrics(region: str) -> pd.DataFrame:
    pop = pd.read_csv(SGIS_POP_PATHS[region], header=None, names=["year", "oa_code", "metric", "value"])
    pop["oa_code"] = pop["oa_code"].astype(str)
    pop = pop[pop["metric"] == "to_in_001"].copy()
    pop["population"] = pd.to_numeric(pop["value"], errors="coerce").fillna(0)
    pop = pop[["oa_code", "population"]]

    emp = pd.read_csv(SGIS_EMP_PATHS[region], header=None, names=["year", "oa_code", "industry", "value"])
    emp["oa_code"] = emp["oa_code"].astype(str)
    emp["employment"] = pd.to_numeric(emp["value"], errors="coerce").fillna(0)
    emp = emp.groupby("oa_code", dropna=False)["employment"].sum().reset_index()

    return pop.merge(emp, on="oa_code", how="outer").fillna({"population": 0, "employment": 0})


def process_sgis(region: str, boundary: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict]:
    sgis = gpd.read_file(SGIS_SHAPE_PATHS[region])
    sgis["TOT_OA_CD"] = sgis["TOT_OA_CD"].astype(str)
    boundary_local = boundary.to_crs(sgis.crs)
    sgis = gpd.overlay(sgis, boundary_local, how="intersection")
    sgis["intersection_area"] = sgis.geometry.area

    original = gpd.read_file(SGIS_SHAPE_PATHS[region])[["TOT_OA_CD", "geometry"]].copy()
    original["original_area"] = original.geometry.area
    sgis = sgis.merge(original[["TOT_OA_CD", "original_area"]], on="TOT_OA_CD", how="left")
    sgis["area_ratio"] = sgis["intersection_area"] / sgis["original_area"]

    metrics = load_sgis_metrics(region).rename(columns={"oa_code": "TOT_OA_CD"})
    sgis = sgis.merge(metrics, on="TOT_OA_CD", how="left")
    sgis["weighted_population"] = sgis["population"].fillna(0) * sgis["area_ratio"].fillna(0)
    sgis["weighted_employment"] = sgis["employment"].fillna(0) * sgis["area_ratio"].fillna(0)

    summary = {
        "population": float(sgis["weighted_population"].sum()),
        "employment": float(sgis["weighted_employment"].sum()),
    }
    return sgis[["TOT_OA_CD", "population", "employment", "area_ratio", "weighted_population", "weighted_employment", "geometry"]], summary


def choose_core_station_nodes(region: str, nodes: pd.DataFrame) -> pd.DataFrame:
    rule = CORE_STATION_RULES[region]
    selected = nodes[nodes["statnm"].astype(str).eq(rule["station_name"])].copy()
    if rule["line_names"]:
        selected = selected[selected["linenm"].astype(str).isin(rule["line_names"])].copy()
    if selected.empty:
        raise ValueError(f"No core station nodes found for {region}")
    return selected


def dijkstra_multi_source(nodes: pd.DataFrame, links: pd.DataFrame, source_ids: list[int]) -> pd.DataFrame:
    adjacency: dict[int, list[tuple[int, float]]] = {}
    for row in links.itertuples(index=False):
        adjacency.setdefault(int(row.fromNode), []).append((int(row.toNode), float(row.timeFT)))
        adjacency.setdefault(int(row.toNode), []).append((int(row.fromNode), float(row.timeTF)))

    dist = {int(node_id): math.inf for node_id in nodes["id"].tolist()}
    heap: list[tuple[float, int]] = []
    for source_id in source_ids:
        dist[source_id] = 0.0
        heapq.heappush(heap, (0.0, source_id))

    while heap:
        current_dist, current = heapq.heappop(heap)
        if current_dist > dist[current]:
            continue
        for nxt, weight in adjacency.get(current, []):
            cand = current_dist + weight
            if cand < dist[nxt]:
                dist[nxt] = cand
                heapq.heappush(heap, (cand, nxt))

    result = nodes.copy()
    result["travel_time_sec"] = result["id"].map(dist)
    result["travel_time_min"] = result["travel_time_sec"] / 60.0
    return result


def service_area_from_stations(stations: gpd.GeoDataFrame, max_minutes: int, buffer_m: int = 600) -> gpd.GeoDataFrame:
    reachable = stations[stations["travel_time_min"] <= max_minutes].copy()
    if reachable.empty:
        return gpd.GeoDataFrame({"minutes": [max_minutes]}, geometry=[None], crs=stations.crs)
    buffered = reachable.to_crs(5179).buffer(buffer_m)
    dissolved = unary_union(buffered.tolist())
    return gpd.GeoDataFrame({"minutes": [max_minutes]}, geometry=[dissolved], crs=5179)


def summarize_service_area(service_area: gpd.GeoDataFrame, sgis_base: gpd.GeoDataFrame) -> dict:
    if service_area.geometry.iloc[0] is None:
        return {"population": 0.0, "employment": 0.0}
    target = service_area.to_crs(sgis_base.crs)
    clipped = gpd.overlay(sgis_base, target, how="intersection")
    if clipped.empty:
        return {"population": 0.0, "employment": 0.0}
    clipped["clip_area"] = clipped.geometry.area
    clipped["weight"] = clipped["clip_area"] / clipped["original_area"]
    return {
        "population": float((clipped["population"] * clipped["weight"]).sum()),
        "employment": float((clipped["employment"] * clipped["weight"]).sum()),
    }


def process_transport(region: str, boundary: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict]:
    nodes, links = load_network()
    selected_nodes = choose_core_station_nodes(region, nodes)
    travel_nodes = dijkstra_multi_source(nodes, links, selected_nodes["id"].astype(int).tolist())

    stations = gpd.GeoDataFrame(
        travel_nodes,
        geometry=gpd.points_from_xy(travel_nodes["lng"], travel_nodes["lat"]),
        crs=4326,
    )

    sgis_base = gpd.read_file(SGIS_SHAPE_PATHS[region])
    sgis_base["TOT_OA_CD"] = sgis_base["TOT_OA_CD"].astype(str)
    metrics = load_sgis_metrics(region).rename(columns={"oa_code": "TOT_OA_CD"})
    sgis_base = sgis_base.merge(metrics, on="TOT_OA_CD", how="left").fillna({"population": 0, "employment": 0})
    sgis_base["original_area"] = sgis_base.to_crs(5179).geometry.area.values

    areas = []
    summaries = {}
    for minute in (30, 60):
        area = service_area_from_stations(stations, minute)
        area = area.to_crs(4326)
        stats = summarize_service_area(area, sgis_base)
        area["population"] = stats["population"]
        area["employment"] = stats["employment"]
        area["core_station"] = selected_nodes["statnm"].iloc[0]
        area["region"] = region
        areas.append(area)
        summaries[str(minute)] = stats

    curve = []
    for minute in range(0, 61, 5):
        area = service_area_from_stations(stations, minute)
        stats = summarize_service_area(area, sgis_base)
        curve.append(
            {
                "minute": minute,
                "population": stats["population"],
                "employment": stats["employment"],
            }
        )

    service_areas = pd.concat(areas, ignore_index=True)
    service_areas = gpd.GeoDataFrame(service_areas, geometry="geometry", crs=4326)
    reachable_stations = stations[stations["travel_time_min"] <= 60].copy()

    metadata = {
        "core_station_name": selected_nodes["statnm"].iloc[0],
        "core_station_lines": sorted(selected_nodes["linenm"].astype(str).unique().tolist()),
        "core_station_node_ids": selected_nodes["id"].astype(int).tolist(),
        "isochrone_totals": summaries,
        "accessibility_curve": curve,
    }
    return service_areas, reachable_stations, metadata


def save_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    if gdf.crs is not None:
        gdf = gdf.to_crs(4326)
    for column in gdf.columns:
        if str(gdf[column].dtype).startswith("datetime"):
            gdf[column] = gdf[column].astype(str)
    path.write_text(gdf.to_json(ensure_ascii=False), encoding="utf-8")


def main() -> None:
    ensure_dir(PROCESSED_DIR)
    summaries = {}

    for region in ("pangyo", "cheongna"):
        region_dir = PROCESSED_DIR / region
        ensure_dir(region_dir)

        boundary = load_boundary(region)
        save_geojson(boundary, region_dir / f"{region}_boundary.geojson")

        landuse_gdf, landuse_summary = process_landuse(region, boundary)
        save_geojson(landuse_gdf, region_dir / f"{region}_landuse.geojson")

        building_gdf, building_summary = process_buildings(region, boundary)
        save_geojson(building_gdf, region_dir / f"{region}_buildings.geojson")

        sgis_gdf, sgis_summary = process_sgis(region, boundary)
        save_geojson(sgis_gdf, region_dir / f"{region}_sgis.geojson")

        service_areas, reachable_stations, transport_meta = process_transport(region, boundary)
        save_geojson(service_areas, region_dir / f"{region}_isochrones.geojson")
        save_geojson(reachable_stations, region_dir / f"{region}_reachable_stations.geojson")

        summaries[region] = {
            "landuse_ratio": landuse_summary,
            "building_use_ratio_by_floor_area": building_summary,
            "sgis_totals": sgis_summary,
            "transport": transport_meta,
        }

    with (PROCESSED_DIR / "summary.json").open("w", encoding="utf-8") as fp:
        json.dump(summaries, fp, ensure_ascii=False, indent=2)

    print(json.dumps(summaries, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
