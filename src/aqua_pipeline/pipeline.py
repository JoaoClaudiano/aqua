from __future__ import annotations

from pathlib import Path
import unicodedata

import geopandas as gpd
from shapely.geometry import box

from .config import PipelineConfig
from .loaders import load_cad_network, load_excel_nodes, load_vector
from .processing import (
    build_node_buffers,
    build_voronoi_areas,
    classify_quantiles,
    ensure_crs,
    join_nodes_with_excel,
)
from .cartography import (
    make_comparison_panel,
    make_location_map,
    make_network_map,
    make_proportional_symbol_map,
    make_voronoi_map,
)


def _normalize_colname(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().strip().split())


def _resolve_column(columns, preferred: str, aliases: list[str]) -> str | None:
    columns = list(columns)
    if preferred in columns:
        return preferred

    normalized_to_original = {_normalize_colname(col): col for col in columns}
    preferred_norm = _normalize_colname(preferred)
    if preferred_norm in normalized_to_original:
        return normalized_to_original[preferred_norm]

    for alias in aliases:
        alias_norm = _normalize_colname(alias)
        if alias_norm in normalized_to_original:
            return normalized_to_original[alias_norm]

    return None


class WaterNetworkMapPipeline:
    """Orquestrador OOP do pipeline SIG para engenharia hidráulica."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _safe_boundary(self, pipes: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Gera limite de fallback quando não existir arquivo de limite."""

        merged = gpd.GeoSeries(list(pipes.geometry) + list(nodes.geometry), crs=pipes.crs)
        minx, miny, maxx, maxy = merged.total_bounds
        pad = self.config.voronoi_clip_buffer_m
        return gpd.GeoDataFrame(geometry=[box(minx - pad, miny - pad, maxx + pad, maxy + pad)], crs=pipes.crs)

    def run(self) -> None:
        """Executa pipeline completo de integração e geração de mapas."""

        pipes, cad_nodes = load_cad_network(self.config.cad_file, source_crs=self.config.source_crs)
        excel_nodes = load_excel_nodes(self.config.nodes_excel)
        excel_node_id_col = _resolve_column(
            excel_nodes.columns,
            self.config.node_id_col_excel,
            ["nó", "no", "node_id", "node id", "node"],
        )

        if pipes.empty:
            raise RuntimeError("Nenhuma tubulação válida encontrada no CAD.")

        if cad_nodes.empty and {"x", "y"}.issubset(set(excel_nodes.columns)):
            if excel_node_id_col is None:
                raise RuntimeError(
                    "A planilha possui x/y, mas não foi possível localizar a coluna de ID nodal para criar os nós."
                )
            cad_nodes = gpd.GeoDataFrame(
                excel_nodes.copy(),
                geometry=gpd.points_from_xy(excel_nodes["x"], excel_nodes["y"]),
                crs=self.config.source_crs,
            )
            cad_nodes[self.config.node_id_col_cad] = cad_nodes[excel_node_id_col].astype(str)

        if cad_nodes.empty:
            raise RuntimeError("Nenhum nó CAD encontrado e a planilha não possui colunas x/y para georreferenciamento.")

        cad_node_id_col = _resolve_column(
            cad_nodes.columns,
            self.config.node_id_col_cad,
            ["node_id", "id_no", "id nó", "nó", "no"],
        )
        if cad_node_id_col is None:
            raise RuntimeError(
                f"Não foi possível localizar coluna de ID nodal no CAD. Colunas disponíveis: {list(cad_nodes.columns)}"
            )
        if excel_node_id_col is None:
            raise RuntimeError(
                f"Não foi possível localizar coluna de ID nodal na planilha. Colunas disponíveis: {list(excel_nodes.columns)}"
            )

        pipes_sirgas = ensure_crs(pipes, self.config.target_crs)
        nodes_sirgas = ensure_crs(cad_nodes, self.config.target_crs)
        nodes_sirgas = join_nodes_with_excel(
            nodes_sirgas,
            excel_nodes,
            node_id_col_cad=cad_node_id_col,
            node_id_col_excel=excel_node_id_col,
        )

        population_col = _resolve_column(
            nodes_sirgas.columns,
            self.config.population_col,
            ["população", "populacao", "pop. do nó (hab)", "pop. do no (hab)", "population"],
        )
        flow_col = _resolve_column(
            nodes_sirgas.columns,
            self.config.flow_col,
            ["vazão nodal qmh (l/s)", "vazao nodal qmh (l/s)", "flow_lps", "qmh área nodal (l/s)"],
        )
        if population_col is None or flow_col is None:
            raise RuntimeError(
                "Não foi possível localizar automaticamente as colunas de população e vazão na planilha após o vínculo."
            )

        nodes_sirgas = classify_quantiles(nodes_sirgas, population_col)
        nodes_sirgas = classify_quantiles(nodes_sirgas, flow_col)

        pipes_metric = pipes_sirgas.to_crs(pipes_sirgas.estimate_utm_crs())
        nodes_metric = nodes_sirgas.to_crs(pipes_metric.crs)

        if self.config.boundary_file:
            boundary = ensure_crs(load_vector(self.config.boundary_file), self.config.target_crs)
            boundary_metric = boundary.to_crs(pipes_metric.crs)
        else:
            boundary_metric = self._safe_boundary(pipes_metric, nodes_metric)
            boundary = boundary_metric.to_crs(self.config.target_crs)

        voronoi_metric = build_voronoi_areas(nodes_metric, boundary_metric)
        buffers_metric = build_node_buffers(nodes_metric, self.config.buffer_distance_m)

        voronoi_sirgas = voronoi_metric.to_crs(self.config.target_crs)
        buffers_sirgas = buffers_metric.to_crs(self.config.target_crs)

        # Exporta dados processados para integração com SIG desktop (QGIS/ArcGIS)
        pipes_sirgas.to_file(self.output_dir / "tubulacoes.gpkg", layer="pipes", driver="GPKG")
        nodes_sirgas.to_file(self.output_dir / "nos.gpkg", layer="nodes", driver="GPKG")
        voronoi_sirgas.to_file(self.output_dir / "areas_influencia.gpkg", layer="voronoi", driver="GPKG")
        buffers_sirgas.to_file(self.output_dir / "buffers_nodais.gpkg", layer="buffers", driver="GPKG")

        make_location_map(
            boundary,
            self.output_dir / "01_mapa_localizacao",
            self.config.export.layout,
            self.config.export.formats,
            self.config.export.dpi,
        )
        make_network_map(
            pipes_metric,
            nodes_metric,
            self.config.dem_file,
            self.output_dir / "02_planta_rede",
            self.config.export.layout,
            self.config.export.formats,
            self.config.export.dpi,
        )
        make_voronoi_map(
            voronoi_metric,
            nodes_metric,
            self.output_dir / "03_areas_influencia",
            self.config.export.layout,
            self.config.export.formats,
            self.config.export.dpi,
        )
        make_proportional_symbol_map(
            nodes_metric,
            population_col,
            "Mapa de População Nodal (Símbolos Proporcionais)",
            self.output_dir / "04_populacao_nodal",
            self.config.export.layout,
            self.config.export.formats,
            self.config.export.dpi,
            cmap="YlGn",
        )
        make_proportional_symbol_map(
            nodes_metric,
            flow_col,
            "Mapa de Vazão Nodal (L/s)",
            self.output_dir / "05_vazao_nodal",
            self.config.export.layout,
            self.config.export.formats,
            self.config.export.dpi,
            cmap="Blues",
        )
        make_comparison_panel(
            nodes_metric,
            population_col,
            flow_col,
            self.output_dir / "06_painel_comparativo",
            self.config.export.layout,
            self.config.export.formats,
            self.config.export.dpi,
        )
