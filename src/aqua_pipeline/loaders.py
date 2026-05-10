from __future__ import annotations

from pathlib import Path

import ezdxf
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point


def load_excel_nodes(path: str | Path) -> pd.DataFrame:
    """Lê planilha com dados nodais."""

    file_path = Path(path)
    if file_path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)
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
            node_features.append(
                {
                    "node_id": entity.dxf.handle,
                    "layer": entity.dxf.layer,
                    "geometry": Point(p.x, p.y),
                }
            )

    pipes = gpd.GeoDataFrame(pipe_features, geometry="geometry", crs=source_crs)
    nodes = gpd.GeoDataFrame(node_features, geometry="geometry", crs=source_crs)
    return pipes, nodes
