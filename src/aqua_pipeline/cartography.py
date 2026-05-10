from __future__ import annotations

from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import contextily as ctx
import geopandas as gpd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import rasterio
from rasterio.plot import plotting_extent


def _layout_size(layout: str) -> tuple[float, float]:
    layout = layout.upper()
    if layout == "A1":
        return (33.1, 23.4)
    return (16.5, 11.7)  # A3 padrão


def _add_north_arrow(ax):
    ax.annotate(
        "N",
        xy=(0.05, 0.9),
        xytext=(0.05, 0.8),
        arrowprops=dict(facecolor="black", width=3, headwidth=12),
        ha="center",
        va="center",
        fontsize=12,
        xycoords="axes fraction",
    )


def _add_scale_bar(ax, length=250):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    bar_x = x0 + (x1 - x0) * 0.05
    bar_y = y0 + (y1 - y0) * 0.05
    ax.plot([bar_x, bar_x + length], [bar_y, bar_y], color="black", lw=3)
    ax.text(bar_x, bar_y, "0", fontsize=8, va="bottom")
    ax.text(bar_x + length, bar_y, f"{length} m", fontsize=8, va="bottom", ha="right")


def _add_dem_contours(ax, dem_file: str | None):
    if not dem_file:
        return
    with rasterio.open(dem_file) as src:
        arr = src.read(1, masked=True)
        ext = plotting_extent(src)

    ny, nx = arr.shape
    xs = np.linspace(ext[0], ext[1], nx)
    ys = np.linspace(ext[2], ext[3], ny)
    X, Y = np.meshgrid(xs, ys)

    try:
        ax.contour(X, Y, arr, levels=10, linewidths=0.4, colors="#6b7280", alpha=0.7)
    except Exception:
        return


def _save(fig, output_stem: Path, formats: list[str], dpi: int):
    for ext in formats:
        fig.savefig(output_stem.with_suffix(f".{ext}"), dpi=dpi, bbox_inches="tight")


def make_location_map(boundary: gpd.GeoDataFrame, output_stem: Path, layout: str, formats: list[str], dpi: int):
    fig, ax = plt.subplots(figsize=_layout_size(layout))
    boundary.to_crs(3857).plot(ax=ax, facecolor="#d9e8c7", edgecolor="#b45309", linewidth=1.5)
    _add_north_arrow(ax)
    _add_scale_bar(ax)
    ax.set_title("Mapa de Localização", fontsize=16, fontweight="bold")
    ax.set_axis_off()
    ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
    _save(fig, output_stem, formats, dpi)
    plt.close(fig)


def make_network_map(
    pipes: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
    dem_file: str | None,
    output_stem: Path,
    layout: str,
    formats: list[str],
    dpi: int,
):
    fig, ax = plt.subplots(figsize=_layout_size(layout))
    pipes.plot(ax=ax, color="#185fa5", linewidth=1.4, label="Tubulações")
    nodes.plot(ax=ax, color="#ef4444", markersize=18, label="Nós")
    _add_dem_contours(ax, dem_file)
    _add_north_arrow(ax)
    _add_scale_bar(ax)
    ax.legend(loc="lower right")
    ax.set_title("Planta da Rede de Abastecimento", fontsize=16, fontweight="bold")
    ax.set_axis_off()
    _save(fig, output_stem, formats, dpi)
    plt.close(fig)


def make_voronoi_map(voronoi: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame, output_stem: Path, layout: str, formats: list[str], dpi: int):
    fig, ax = plt.subplots(figsize=_layout_size(layout))
    voronoi.plot(ax=ax, cmap="Pastel1", alpha=0.7, edgecolor="#6b7280", linewidth=0.7)
    nodes.plot(ax=ax, color="#1f2937", markersize=14)
    _add_north_arrow(ax)
    _add_scale_bar(ax)
    ax.set_title("Áreas de Influência (Voronoi/Thiessen)", fontsize=16, fontweight="bold")
    ax.set_axis_off()
    _save(fig, output_stem, formats, dpi)
    plt.close(fig)


def make_proportional_symbol_map(
    nodes: gpd.GeoDataFrame,
    value_col: str,
    title: str,
    output_stem: Path,
    layout: str,
    formats: list[str],
    dpi: int,
    cmap: str = "viridis",
):
    fig, ax = plt.subplots(figsize=_layout_size(layout))
    vals = nodes[value_col].fillna(0)
    sizes = (vals.clip(lower=0) + 1) * 6
    nodes.plot(ax=ax, column=value_col, cmap=cmap, markersize=sizes, alpha=0.75, legend=True)

    _add_north_arrow(ax)
    _add_scale_bar(ax)
    ax.set_title(title, fontsize=16, fontweight="bold")
    ax.set_axis_off()
    _save(fig, output_stem, formats, dpi)
    plt.close(fig)


def make_comparison_panel(
    nodes,
    population_col: str,
    flow_col: str,
    output_stem: Path,
    layout: str,
    formats: list[str],
    dpi: int,
):
    fig, axes = plt.subplots(2, 2, figsize=_layout_size(layout))
    fig.suptitle("Painel Comparativo — População x Vazão", fontsize=16, fontweight="bold")

    pop = nodes[[population_col]].fillna(0)
    flow = nodes[[flow_col]].fillna(0)

    axes[0, 0].hist(pop[population_col], bins=10, color="#22c55e")
    axes[0, 0].set_title("Distribuição de População")

    axes[0, 1].hist(flow[flow_col], bins=10, color="#0ea5e9")
    axes[0, 1].set_title("Distribuição de Vazão (L/s)")

    axes[1, 0].scatter(pop[population_col], flow[flow_col], color="#334155", alpha=0.7)
    axes[1, 0].set_xlabel("População")
    axes[1, 0].set_ylabel("Vazão (L/s)")
    axes[1, 0].set_title("Correlação Nodal")

    axes[1, 1].axis("off")
    total_pop = float(pop[population_col].sum())
    total_flow = float(flow[flow_col].sum())
    mean_flow = float(flow[flow_col].mean())
    table_data = [
        ["Nós", str(len(nodes))],
        ["População Total", f"{total_pop:,.0f}"],
        ["Vazão Total (L/s)", f"{total_flow:,.2f}"],
        ["Vazão Média (L/s)", f"{mean_flow:,.2f}"],
    ]
    tbl = axes[1, 1].table(cellText=table_data, colLabels=["Indicador", "Valor"], loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 1.5)

    _save(fig, output_stem, formats, dpi)
    plt.close(fig)
