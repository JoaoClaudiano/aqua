from __future__ import annotations

import numpy as np
import geopandas as gpd
import pandas as pd
from scipy.spatial import Voronoi
from shapely.geometry import Polygon


def ensure_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    """Reprojeta camada para CRS alvo, se necessário."""

    if gdf.empty:
        return gdf
    if gdf.crs is None:
        raise ValueError("Camada sem CRS definido.")
    return gdf.to_crs(target_crs) if str(gdf.crs) != target_crs else gdf


def join_nodes_with_excel(
    nodes: gpd.GeoDataFrame,
    excel_df: pd.DataFrame,
    node_id_col_cad: str,
    node_id_col_excel: str,
) -> gpd.GeoDataFrame:
    """Vincula atributos da planilha aos nós por ID."""

    if nodes.empty:
        return nodes

    nodes = nodes.copy()
    nodes[node_id_col_cad] = nodes[node_id_col_cad].astype(str)
    excel = excel_df.copy()
    excel[node_id_col_excel] = excel[node_id_col_excel].astype(str)

    merged = nodes.merge(
        excel,
        left_on=node_id_col_cad,
        right_on=node_id_col_excel,
        how="left",
        suffixes=("", "_xls"),
    )
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=nodes.crs)


def classify_quantiles(gdf: gpd.GeoDataFrame, col: str, k: int = 5) -> gpd.GeoDataFrame:
    """Classificação temática automática por quantis."""

    if gdf.empty or col not in gdf.columns:
        return gdf

    series = pd.to_numeric(gdf[col], errors="coerce")
    valid = series.dropna()
    if valid.nunique() <= 1:
        gdf[f"{col}_class"] = "única"
        return gdf

    gdf[f"{col}_class"] = pd.qcut(series, q=min(k, valid.nunique()), duplicates="drop").astype(str)
    return gdf


def build_node_buffers(nodes_metric: gpd.GeoDataFrame, distance_m: float) -> gpd.GeoDataFrame:
    """Gera buffers automáticos em torno dos nós."""

    if nodes_metric.empty:
        return nodes_metric

    buff = nodes_metric.copy()
    buff["geometry"] = buff.geometry.buffer(distance_m)
    return buff


def _voronoi_finite_polygons_2d(vor: Voronoi, radius: float | None = None):
    """Reconstrói regiões Voronoi infinitas para polígonos finitos."""

    if vor.points.shape[1] != 2:
        raise ValueError("Voronoi 2D esperado")

    new_regions = []
    new_vertices = vor.vertices.tolist()

    center = vor.points.mean(axis=0)
    radius = radius or (np.ptp(vor.points, axis=0).max() * 2)

    all_ridges: dict[int, list[tuple[int, int, int]]] = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        all_ridges.setdefault(p1, []).append((p2, v1, v2))
        all_ridges.setdefault(p2, []).append((p1, v1, v2))

    for p1, region_idx in enumerate(vor.point_region):
        vertices = vor.regions[region_idx]

        if all(v >= 0 for v in vertices):
            new_regions.append(vertices)
            continue

        ridges = all_ridges[p1]
        new_region = [v for v in vertices if v >= 0]

        for p2, v1, v2 in ridges:
            if v2 < 0:
                v1, v2 = v2, v1
            if v1 >= 0:
                continue

            tangent = vor.points[p2] - vor.points[p1]
            tangent /= np.linalg.norm(tangent)
            normal = np.array([-tangent[1], tangent[0]])

            midpoint = vor.points[[p1, p2]].mean(axis=0)
            direction = np.sign(np.dot(midpoint - center, normal)) * normal
            far_point = vor.vertices[v2] + direction * radius

            new_region.append(len(new_vertices))
            new_vertices.append(far_point.tolist())

        vs = np.asarray([new_vertices[v] for v in new_region])
        c = vs.mean(axis=0)
        angles = np.arctan2(vs[:, 1] - c[1], vs[:, 0] - c[0])
        new_region = np.array(new_region)[np.argsort(angles)].tolist()
        new_regions.append(new_region)

    return new_regions, np.asarray(new_vertices)


def build_voronoi_areas(nodes_metric: gpd.GeoDataFrame, clip_polygon: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Gera polígonos de Voronoi/Thiessen para áreas nodais."""

    if nodes_metric.empty:
        return gpd.GeoDataFrame(geometry=[], crs=nodes_metric.crs)

    coords = np.array([(geom.x, geom.y) for geom in nodes_metric.geometry])
    if len(coords) < 3:
        simple = nodes_metric.copy()
        simple["geometry"] = simple.geometry.buffer(50)
        return simple

    vor = Voronoi(coords)
    regions, vertices = _voronoi_finite_polygons_2d(vor)

    polygons = []
    for region in regions:
        polygon = Polygon(vertices[region])
        polygons.append(polygon)

    vor_gdf = gpd.GeoDataFrame({"node_idx": list(range(len(polygons)))}, geometry=polygons, crs=nodes_metric.crs)

    clip_geom = clip_polygon.unary_union
    vor_gdf["geometry"] = vor_gdf.geometry.intersection(clip_geom)
    vor_gdf = vor_gdf[~vor_gdf.geometry.is_empty].copy()
    return vor_gdf
