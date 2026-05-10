# Pipeline SIG para Rede de Abastecimento de Água

Sistema em Python para geração automática de mapas técnicos de rede de abastecimento usando CAD (DXF), GIS e Excel.

## Estrutura

- `input/`: dados de entrada (DXF, shapefiles/GeoJSON/GeoTIFF, Excel)
- `output/`: mapas e camadas processadas
- `src/aqua_pipeline/`: scripts modulares orientados a objetos
- `scripts/run_pipeline.py`: execução via CLI
- `config.example.yaml` / `config.example.json`: parâmetros configuráveis

## Funcionalidades implementadas

- Leitura de **DXF**, vetores GIS e planilhas Excel
- Conversão de entidades CAD para geometrias GIS (tubulações e nós)
- Vinculação de dados nodais por ID (Excel ↔ nós)
- Reprojeção automática para **SIRGAS 2000 (EPSG:4674)**
- Geração automática de:
  1. mapa de localização
  2. planta da rede
  3. áreas de influência por Voronoi/Thiessen
  4. mapa de população nodal (símbolos proporcionais)
  5. mapa de vazão nodal
  6. painel comparativo com gráficos e tabela
- Geração automática de buffers nodais
- Classificação temática automática por quantis
- Layout A1/A3, seta norte, escala gráfica, legenda e exportação PNG/PDF (300 dpi)
- Curvas de nível a partir de GeoTIFF (quando informado `dem_file`)

## Instalação

```bash
pip install -r requirements.txt
```

## Execução

```bash
python scripts/run_pipeline.py --config config.example.yaml
```

## Observações

- Arquivos **DWG** devem ser convertidos para DXF antes da execução (limitação do `ezdxf`).
- IDs nodais no CAD e no Excel devem corresponder para o vínculo automático.
