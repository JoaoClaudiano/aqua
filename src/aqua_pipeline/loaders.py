from __future__ import annotations

from pathlib import Path
import re
import unicodedata

import ezdxf
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point

NODE_LABEL_PATTERN = re.compile(r"^N\s*\d+$", re.IGNORECASE)
NODE_ID_ALIASES = {"node_id", "node id", "node", "no", "no.", "nó", "id_no", "id no", "id nó"}


def _normalize_text(value) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("\n", " ").split())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text.lower().strip()


def _normalize_node_label(label: str) -> str:
    return re.sub(r"\s+", "", label).upper()


def _load_excel_best_sheet(path: Path) -> pd.DataFrame:
    workbook = pd.ExcelFile(path)
    best_table: pd.DataFrame | None = None
    best_score = -1.0

    for sheet_name in workbook.sheet_names:
        raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
        if raw.empty:
            continue

        max_header_scan = min(len(raw), 60)
        header_idx: int | None = None
        for idx in range(max_header_scan):
            normalized_row = [_normalize_text(v) for v in raw.iloc[idx].tolist()]
            if any(cell in NODE_ID_ALIASES for cell in normalized_row):
                header_idx = idx
                break

        if header_idx is None:
            continue

        raw_headers = raw.iloc[header_idx].tolist()
        headers: list[str] = []
        for i, header in enumerate(raw_headers):
            header_text = "" if pd.isna(header) else str(header).strip()
            if not header_text or _normalize_text(header_text).startswith("unnamed"):
                header_text = f"col_{i}"
            headers.append(header_text)

        table = raw.iloc[header_idx + 1 :].copy()
        table.columns = headers
        table = table.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
        if table.empty:
            continue

        normalized_columns = {_normalize_text(col): col for col in table.columns}
        score = 0.0
        node_col_name = next((original for norm, original in normalized_columns.items() if norm in NODE_ID_ALIASES), None)
        if node_col_name:
            score += 2.0
            node_values = (
                table[node_col_name]
                .astype(str)
                .str.replace(r"\s+", "", regex=True)
                .str.upper()
            )
            score += min(float(node_values.str.match(r"^N\d+$", na=False).sum()) / 100.0, 1.5)

        if any(("vazao" in norm) or ("flow" in norm) or ("qmh" in norm) for norm in normalized_columns):
            score += 1.0
        if any("pop" in norm for norm in normalized_columns):
            score += 1.0

        if score > best_score:
            best_table = table
            best_score = score

    if best_table is not None:
        return best_table

    return pd.read_excel(path)


def load_excel_nodes(path: str | Path) -> pd.DataFrame:
    """Lê planilha com dados nodais."""

    file_path = Path(path)
    if file_path.suffix.lower() in {".xlsx", ".xls"}:
        return _load_excel_best_sheet(file_path)
    if file_path.suffix.lower() == ".csv":
        return pd.read_csv(file_path)
    raise ValueError(f"Formato de planilha não suportado: {file_path.suffix}")


def load_vector(path: str | Path) -> gpd.GeoDataFrame:
    """Lê shapefile/GeoJSON (ou qualquer vetor suportado pelo GDAL)."""

    return gpd.read_file(path)


def load_cad_network(path: str | Path, source_crs: str = "EPSG:31984") -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Converte entidades CAD em camadas GIS (tubulações e nós)."""

    cad_path = Path(path)
    if cad_path.suffix.lower() == ".dwg":
        raise ValueError("DWG não é lido diretamente por ezdxf. Converta para DXF antes de executar.")

    doc = ezdxf.readfile(str(cad_path))
    msp = doc.modelspace()

    pipe_features: list[dict] = []
    node_features: list[dict] = []
    node_ids_seen: set[str] = set()

    for entity in msp:
        etype = entity.dxftype()

        if etype == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            pipe_features.append(
                {
                    "cad_id": entity.dxf.handle,
                    "layer": entity.dxf.layer,
                    "geometry": LineString([(start.x, start.y), (end.x, end.y)]),
                }
            )

        elif etype == "LWPOLYLINE":
            points = [(p[0], p[1]) for p in entity.get_points()]
            if len(points) >= 2:
                pipe_features.append(
                    {
                        "cad_id": entity.dxf.handle,
                        "layer": entity.dxf.layer,
                        "geometry": LineString(points),
                    }
                )

        elif etype == "POLYLINE":
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
            if len(points) >= 2:
                pipe_features.append(
                    {
                        "cad_id": entity.dxf.handle,
                        "layer": entity.dxf.layer,
                        "geometry": LineString(points),
                    }
                )

        elif etype == "POINT":
            p = entity.dxf.location
            node_id = str(entity.dxf.handle)
            node_features.append(
                {
                    "node_id": node_id,
                    "layer": entity.dxf.layer,
                    "geometry": Point(p.x, p.y),
                }
            )
            node_ids_seen.add(node_id)

        elif etype in {"TEXT", "MTEXT"}:
            text_value = entity.dxf.text if etype == "TEXT" else entity.text
            text_value = "" if text_value is None else str(text_value).replace("\\P", " ").strip()
            if not NODE_LABEL_PATTERN.match(text_value):
                continue

            node_id = _normalize_node_label(text_value)
            if node_id in node_ids_seen:
                continue

            insertion_point = entity.dxf.insert
            node_features.append(
                {
                    "node_id": node_id,
                    "layer": entity.dxf.layer,
                    "geometry": Point(insertion_point.x, insertion_point.y),
                }
            )
            node_ids_seen.add(node_id)

    if pipe_features:
        pipes = gpd.GeoDataFrame(pipe_features, geometry="geometry", crs=source_crs)
    else:
        pipes = gpd.GeoDataFrame(pd.DataFrame(columns=["cad_id", "layer", "geometry"]), geometry="geometry", crs=source_crs)

    if node_features:
        nodes = gpd.GeoDataFrame(node_features, geometry="geometry", crs=source_crs)
    else:
        nodes = gpd.GeoDataFrame(pd.DataFrame(columns=["node_id", "layer", "geometry"]), geometry="geometry", crs=source_crs)

    return pipes, nodes
