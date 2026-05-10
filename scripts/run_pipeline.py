#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aqua_pipeline import WaterNetworkMapPipeline, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline SIG para mapas técnicos de rede de água")
    parser.add_argument("--config", required=True, help="Caminho do arquivo YAML/JSON de configuração")
    args = parser.parse_args()

    cfg = load_config(args.config)
    pipeline = WaterNetworkMapPipeline(cfg)
    pipeline.run()
    print(f"Pipeline concluído. Resultados em: {cfg.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
