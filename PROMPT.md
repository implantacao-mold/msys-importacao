# Contexto do Projeto — MSYS Importação de Dados

Use este arquivo para iniciar uma nova sessão com contexto completo do projeto.

---

## O que é

Ferramenta desktop (interface web local em Flask) para converter backups de sistemas imobiliários para o formato de importação do **Msys Imob**. Roda em `http://127.0.0.1:5000`.

**Pasta do projeto:** `C:\Projetos Claude\Migração de dados\`

**Para rodar:** `iniciar.bat` (ou `python main.py`)

---

## Arquitetura

```
Browser (gui/templates/index.html + gui/static/app.js)
  → POST /api/export  (gui/web_server.py — Flask)
    → ExportEngine.run() / run_zip()   (core/engine.py)
      → mapper.extract() / extract_zip()   (mappers/<sistema>.py)
        → ExtractionResult { persons, emails, phones, property_result? }
    → exporter.export()   (core/exporter.py)
      → PERSON/PERSON.csv, EMAIL.csv, PHONE.csv
      → if property_result: export_properties() → PROPERTY/*.csv
  → GET /api/job/<id>  (polling 800 ms)
  → GET /api/download/<token>  (ZIP, one-time)
```

---

## Mappers registrados

| Sistema | Formato | Exporta imóveis |
|---------|---------|----------------|
| Arbo | XML | Sim |
| Code49 | XML | Não |
| Imobi Brasil | XML | Sim |
| Imobzi | ZIP (JSONs) | Sim |
| Kenlo | ZIP (XLSX) | Não |
| Msys Imob | SQL / ZIP | Não |
| Tec Imob | XLSX multi-aba | Sim |
| Univen | ZIP (XMLs) | Não |
| Vista CRM | ZIP (SQL) | Não |

---

## Regras obrigatórias (SEMPRE respeitar)

### Encoding e formato de saída
- Todos os CSVs: encoding **cp1252**, separador **`;`**
- Subpasta `PERSON/` para pessoas, `PROPERTY/` para imóveis
- `_sanitize(v)` é chamado em todos os campos ao gravar: normaliza NFC, decodifica entidades HTML/XML (`&#xA;`, `&amp;` etc.), remove `\n \r \t`

### CPF/CNPJ
- Todo campo de documento escrito no CSV recebe prefixo `'` (apóstrofo) via `_q(v)` — somente nos exporters, nunca nos mappers

### CEP (automático — mappers não precisam fazer nada)
- `core/exporter.py` e `core/property_exporter.py` chamam `fix_record_cep(record)` em todos os records antes de gravar
- Regra: strip não-dígitos → CEP válido (8 dígitos, não `00000000`/`99999999`) → `fill_city_state` → CEP inválido/incompleto/placeholder → `lookup_cep_by_city(cidade, estado)`
- Mappers só precisam popular `p.cep`, `p.cidade`, `p.estado` com o que vier da fonte

### data_captacao (automático — mappers não precisam fazer nada)
- `core/property_exporter.py` copia `PropertyRecord.data_registro → PropertyCaptivatorRecord.data_captacao` para todos os captivadores antes de gravar
- Mappers só precisam popular `pr.data_registro` corretamente

### Tipo EM (Colaborador)
- Nunca emitir `PersonRecord` com `tipo="EM"` sem `cpf` ou `cnpj` não-vazio

### Sexo
- `"F"` para `"Feminino"/"female"/"f"` (case-insensitive); `"M"` para qualquer outro não-vazio

### Valores monetários e áreas
- Helper `_fmt_val(v)` → `f"{f:.2f}"` ou `""` se zero/nulo

### HTML em textos
- `re.sub(r"<[^>]+>", " ", text)` + `html.unescape()` + normalização de espaços

### Endereço (imóveis)
- `normalize_address(bairro, rua, numero, complemento)` — bairro/rua vazios → `"Não Informado"`, numero vazio → `"0"`, numero com letras → move para complemento

### Subcategoria
- Cadeia: dict do mapper → keyword inference → `tipoimovel` secondary lookup → default `"7"` (Casa Padrão)
- Custom via `data/custom_subcategorias.json` (UI de revisão no card 5)

### Características
- `build_sim_nao(feature_names)` → `pr.caracteristicas_sim_nao` (índice 121)
- `map_characteristics_to_fields(feature_names)` → `setattr(pr, field, qty)` apenas se campo vazio
- Custom via `data/custom_caracteristicas.json` (UI de revisão no card 5)

---

## Arquivos principais

```
main.py                         Ponto de entrada, abre browser
iniciar.bat                     Launcher Windows (verifica Python, instala deps, inicia)
requirements.txt                flask, openpyxl, pytest, mysql-connector-python

core/
  engine.py                     Orquestra carga + execução do mapper
  exporter.py                   Grava PERSON.csv, EMAIL.csv, PHONE.csv
  property_exporter.py          Grava PROPERTY/*.csv (aplica fix_record_cep + data_captacao)
  cep_lookup.py                 lookup_cep, lookup_cep_by_city, fill_city_state, fix_record_cep, is_valid_cep
  base_mapper.py                BaseMapper ABC + ExtractionResult + PersonRecord etc.
  property_records.py           PropertyRecord (137 cols), normalize_address, PropertyExtractionResult
  caracteristicas.py            CARACTERISTICAS_COMBOBOX (dict id→nome)
  subcategorias.py              SUBCATEGORIAS (dict id→(tipo,subtipo)) + custom persistence
  characteristics_utils.py      match_feature, build_sim_nao, map_characteristics_to_fields, _ID_TO_FIELD
  schema.py                     ENCODING, SEPARATOR, colunas dos CSVs

mappers/
  _template.py                  Template para novos mappers
  arbo.py                       XML — pessoas + imóveis
  code49.py                     XML — só pessoas
  imobi_brasil.py               XML — pessoas + imóveis
  imobzi.py                     ZIP (JSONs) — pessoas + imóveis
  kenlo.py                      ZIP (XLSX) — só pessoas
  msys_imob.py                  SQL/ZIP — só pessoas
  tec_imob.py                   XLSX multi-aba — pessoas + imóveis
  univen.py                     ZIP (XMLs) — só pessoas
  vista.py                      ZIP (SQL) — só pessoas

gui/
  web_server.py                 Flask: /api/export, /api/scan, /api/browse-folder, /api/open-folder, /api/mappings/*
  templates/index.html          UI (5 cards: arquivo, sistema, imobiliária, destino, revisão)
  static/app.js                 Lógica de UI (scan, combos, export polling)
  static/style.css              Dark/light theme

data/
  db_config.json                Credenciais MySQL (NÃO versionar — ver db_config.json.example)
  cep_cache.json                Cache local de CEPs consultados
  custom_caracteristicas.json   Mapeamentos manuais de características
  custom_subcategorias.json     Mapeamentos manuais de subcategorias

tests/                          pytest — um arquivo por mapper
```

---

## Como adicionar um novo mapper

1. Copie `mappers/_template.py` → `mappers/<sistema>.py`
2. Defina `NAME`, `EXTENSIONS`, `DESCRIPTION`
3. Implemente `extract(data)` ou `extract_zip(files: dict)`
4. Registre em `mappers/__init__.py` dentro de `build_engine()` (ordem alfabética por NAME)
5. **Não** chamar `fill_city_state` / `lookup_cep_by_city` — o exporter faz automaticamente
6. **Não** setar `data_captacao` — o exporter copia de `data_registro` automaticamente
7. Para imóveis: popular `PropertyExtractionResult` e atribuir a `result.property_result`

---

## Controle de versão

Repositório Git. Para contribuir:
```bash
git clone <url-do-repo>
pip install -r requirements.txt
cp data/db_config.json.example data/db_config.json  # preencher credenciais
python main.py
pytest tests/ -q
```
