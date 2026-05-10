from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class ExportConfig:
    """Configuração de layout/exportação cartográfica."""

    layout: str = "A3"  # A1 ou A3
    dpi: int = 300
    formats: list[str] = field(default_factory=lambda: ["png", "pdf"])


@dataclass
class PipelineConfig:
    """Parâmetros globais do pipeline SIG."""

    cad_file: str
    nodes_excel: str
    output_dir: str = "output"
    gis_network_file: str | None = None
    boundary_file: str | None = None
    dem_file: str | None = None
    source_crs: str = "EPSG:31984"
    target_crs: str = "EPSG:4674"  # SIRGAS 2000
    node_id_col_excel: str = "node_id"
    node_id_col_cad: str = "node_id"
    population_col: str = "population"
    flow_col: str = "flow_lps"
    buffer_distance_m: float = 50.0
    voronoi_clip_buffer_m: float = 300.0
    export: ExportConfig = field(default_factory=ExportConfig)


def load_config(config_path: str | Path) -> PipelineConfig:
    """Carrega arquivo de configuração YAML/JSON."""

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {path}")

    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML não está instalado. Use JSON ou instale pyyaml.")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError("Formato de configuração inválido. Use YAML ou JSON.")

    export_data = data.pop("export", {}) if data else {}
    export_cfg = ExportConfig(**export_data)
    return PipelineConfig(export=export_cfg, **data)
