# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the application

```bash
pip install -r requirements.txt
python main.py
# Opens http://127.0.0.1:5000 automatically in the browser
```

## Architecture

This is a data migration tool (web UI on localhost) that reads files from various Brazilian real estate systems and writes standardized CSVs for import into **Msys Imob**.

### Data flow

```
Browser (gui/templates/index.html + gui/static/app.js)
  → POST /api/export  (gui/web_server.py — Flask)
    → ExportEngine.run() / run_zip()   (core/engine.py)
      → mapper.extract() / extract_zip()   (mappers/<system>.py)
        → ExtractionResult { persons, emails, phones, property_result? }
    → exporter.export()   (core/exporter.py)
      → PERSON/PERSON.csv, EMAIL.csv, PHONE.csv
      → if property_result: export_properties() → PROPERTY/*.csv
  → GET /api/job/<id>  (polling, 800 ms interval)
  → GET /api/download/<token>  (serves result ZIP, one-time)
```

### Web server (`gui/web_server.py`)

`create_app()` returns a Flask app. Jobs are tracked in an in-memory dict `jobs: dict[str, JobState]`. Each export runs in a daemon thread. Uploaded files go to a `tempfile.mkdtemp()` folder and are deleted in the thread's `finally` block. Result ZIPs are served once then deleted via `response.call_on_close`.

Two output modes: `"download"` (browser downloads a ZIP) and `"path"` (CSVs written to a user-supplied local path).

### Context pipeline

The UI form collects `imob_cpf_cnpj` and `imob_nome` (real estate agency fallback data) and sends them as FormData fields. `web_server.py` extracts them, builds a `context` dict, and passes it to `engine.run()` / `engine.run_zip()`, which sets `mapper.context` before calling `extract()`. Mappers that don't need context simply ignore it.

### Key contracts

**`BaseMapper` (core/base_mapper.py):** Every mapper implements `NAME`, `EXTENSIONS`, `DESCRIPTION`, and either `extract(data)` for single files or `extract_zip(files: dict)` for ZIP archives. `extract()` receives parsed data (ET.Element for XML, list[dict] or dict[sheet→list] for XLSX, str for SQL). `extract_zip()` receives `{basename: parsed_data}`. The `context: dict` class attribute is populated by ExportEngine before every extract call.

**`ExtractionResult`:** Contains `persons: list[PersonRecord]`, `emails: list[EmailRecord]`, `phones: list[PhoneRecord]`, and `property_result: PropertyExtractionResult | None`. Imobzi and Imobi Brasil populate `property_result`.

**XLSX multi-sheet:** `engine.load_file()` returns `list[dict]` for single-sheet XLSX and `dict[sheet_name, list[dict]]` for multi-sheet. Tec Imob relies on this — its mapper must handle both types.

**Deduplication key:** `f"{codigo}|{tipo}"`. Same person with multiple roles generates one `PersonRecord` per role (use `dataclasses.replace()` to copy with only `tipo` changed).

### Output encoding

All CSVs use **cp1252** encoding and **`;`** as delimiter. Input XLSX data must be NFC-normalized before writing (NFD acentos from XLSX break cp1252). See `core/exporter.py` `_sanitize()`.

### Person type codes

`OW`=Proprietário, `BU`=Comprador, `OC`=Locatário, `GU`=Fiador, `FA`=Favorecido, `EM`=Colaborador.

### Mandatory rules for all mappers

**EM (Colaborador) only with CPF/CNPJ:** Never emit a `PersonRecord` with `tipo="EM"` unless `cpf` or `cnpj` is non-empty after stripping non-digits. Skip the record silently.

**CPF/CNPJ single-quote prefix:** All CPF/CNPJ fields written to CSV must be prefixed with `'` (single apostrophe) so spreadsheet importers treat them as text and preserve leading zeros. Use the `_q(v)` helper defined in `core/exporter.py` and `core/property_exporter.py`. Applies to every document field in every exporter — do not add the prefix inside mappers, only in exporters.

**CEP — never hardcode a fallback:** If the source record has no CEP, set `cep = ""`. Never substitute a placeholder ZIP code. Populate `p.cep`, `p.cidade`, `p.estado` with whatever comes from the source and leave normalization to the exporter (see below).

**CEP normalization is automatic — mappers do NOT need to call fill_city_state or lookup_cep_by_city.** `core/exporter.py` and `core/property_exporter.py` call `fix_record_cep(record)` (from `core/cep_lookup.py`) on every person and property record before writing the CSV. `fix_record_cep` applies: (1) strip non-digits; (2) if valid 8-digit non-placeholder CEP → `fill_city_state` to complete missing cidade/estado; (3) if CEP missing, incomplete (< 8 digits), or placeholder (`"00000000"`, `"99999999"`) → `lookup_cep_by_city(cidade, estado)` fallback. Any `fill_city_state` / `lookup_cep_by_city` calls left inside individual mappers are harmless (results are cached) but redundant.

**CEP lookup via MySQL:** `core/cep_lookup.py` queries `69.164.204.101:3306` (schema `address-postoffice`, table `address`, columns `num_postal_code`, `nam_city`, `sgl_uf`). Connection config is in `data/db_config.json`. A local JSON cache (`data/cep_cache.json`) avoids repeated queries. A singleton connection is reused across calls; on failure the function returns `None` without blocking the export.

**Profissão and Órgão Expedidor normalization is automatic — mappers do NOT set these.** `core/exporter.py` calls `resolve_profession(p.profissao)` and `resolve_orgao(p.orgao_expedidor)` (from `core/profession_utils.py`) for every `PersonRecord`. Logic: exact/high-score match (≥ 0.92 for profissões, ≥ 0.85 for órgãos) → replaces with canonical name from `data/profissoes.json` / `data/orgaos_expedidores.json`; medium score → shown in Card 5 review for user decision; no match → keeps original. User decisions persist in `data/custom_profissoes.json` and `data/custom_orgaos.json`.

**Sexo mapping:** Map the source gender field to `"F"` when the value is `"Feminino"`, `"female"`, or `"f"` (case-insensitive). Map to `"M"` for any other non-empty value. Leave empty if the source field is absent.

**Monetary and area values — 2 decimal places:** Use a `_fmt_val(v)` helper (defined in each mapper that needs it) that converts numeric values to `f"{f:.2f}"` and returns `""` for zero, null, or unparseable input. Apply to: `valor_venda`, `valor_locacao`, `valor_condominio`, `area_util`, `area_total`, `area_construida`, `iptu` values, and all similar numeric fields.

**HTML stripping:** Strip HTML tags and decode HTML entities from any text field that may contain rich-text markup (descriptions, observations). Use a helper equivalent to `re.sub(r"<[^>]+>", " ", text)` followed by `html.unescape()` and whitespace normalization.

**Person address fields:** Always populate `cep`, `cidade`, `bairro`, `estado`, `endereco`, `numero`, `profissao`, `nacionalidade` on `PersonRecord` when the source provides them. Call `fill_city_state` after extracting `cep`/`cidade`/`estado`. Strip non-digits from CEP.

### Shared reference modules

**`core/subcategorias.py`** — `SUBCATEGORIAS: dict[int, tuple[str, str]]` with 72 official Msys Imob subcategories. Each mapper maintains its own source→ID mapping dict using these IDs as values.

**`core/caracteristicas.py`** — `CARACTERISTICAS_COMBOBOX: dict[int, str]` with all characteristics where `flg_load_in_combobox = 1`. These are the only characteristics that go into column DQ (`caracteristicas_sim_nao`, index 120) of the property file.

### Characteristics matching (`core/characteristics_utils.py`)

`match_feature(name: str) -> str | None` — matches an incoming feature name to the canonical Msys name using 4 strategies: exact case-insensitive, English→Portuguese dictionary, difflib without accents (cutoff 0.65), difflib with accents (cutoff 0.65). Returns `None` if not found — unmatched features must not be included in the export.

`build_sim_nao(feature_names: list[str]) -> str` — converts a list of raw feature names to a comma-separated string of canonical names for the "Outras características" column (index 121). Skips `None` matches and deduplicates.

`_ID_TO_FIELD: dict[int, str]` — authoritative mapping from Msys characteristic ID → `PropertyRecord` field name. Reference for all systems.

`map_characteristics_by_id(id_qty_pairs) -> dict[str, str]` — for systems that provide Msys characteristic IDs directly; maps `(id, qty)` pairs to `{field: qty}` using `_ID_TO_FIELD`.

### Address normalization (`core/property_records.py`)

`normalize_address(bairro, rua, numero, complemento) -> tuple[str, str, str, str]` — applied in every mapper that exports properties. Rules: blank bairro/rua → `"Não Informado"`; blank numero → `"0"`; numero with non-digit characters → move to complemento as `"Nº <original>"` and zero the field.

### Subcategory fallback chain

All property mappers resolve subcategoria via a 4-step chain: exact dict match → keyword inference (ordered from specific to generic) → `tipoimovel` secondary lookup → default `"7"` (Casa Padrão).

### Adding a new mapper

1. Copy `mappers/_template.py` → `mappers/<system>.py`
2. Set `NAME`, `EXTENSIONS`, `DESCRIPTION`; implement `extract()` or `extract_zip()`
3. Register in `mappers/__init__.py` inside `build_engine()` — the list is sorted alphabetically by `NAME`

### Adding property export to a mapper

Populate a `PropertyExtractionResult` (core/property_records.py) with the 5 lists and assign to `result.property_result`. The exporter handles the rest. Column layout for `PropertyRecord.to_row()` is fixed at **137 columns** — index 120 is `"Caracteristicas Sim/Nao"`.

Use `normalize_address()` when populating address fields. Use IDs from `core/subcategorias.py` for `sub_categoria`.

**Characteristics — mandatory for every mapper that exports properties:**
1. Call `build_sim_nao(feature_names)` → assign result to `pr.caracteristicas_sim_nao` ("Outras características", index 121).
2. Call `map_characteristics_to_fields(feature_names)` → for each `(field, qty)` returned, set `setattr(pr, field, qty)` only when the field is still empty (never overwrite values already filled from dedicated source fields).
Both functions are in `core/characteristics_utils.py`. Import both: `from core.characteristics_utils import build_sim_nao, map_characteristics_to_fields`.

When the mapper has no owner data, fall back to `self.context.get("imob_cpf_cnpj")` and `self.context.get("imob_nome")` for `PropertyOwnerRecord`, `PropertyOwnerFavoredRecord`, and `PropertyCaptivatorRecord`.

**`data_captacao` is always automatic — do NOT set it in mappers.** `core/property_exporter.py` copies `PropertyRecord.data_registro` → `PropertyCaptivatorRecord.data_captacao` for every captivator before writing the CSV. Mappers only need to populate `pr.data_registro` correctly.

**Imóvel SL → 2 captivadores automáticos.** `core/property_exporter.py` expande automaticamente cada `PropertyCaptivatorRecord` cujo imóvel tenha `tipo="SL"` e `departamento` ainda não seja `"S"` ou `"L"`, gerando dois registros: um com `departamento="S"` e outro com `departamento="L"`. Mappers não precisam fazer essa duplicação — basta emitir um único captivador por imóvel.

### Imobzi-specific

- Paginated JSON files (`person-1.json`, `person-2.json`, …) are aggregated by `_collect(files, prefix)` in `mappers/imobzi.py`.
- Person/org `codigo` = `_id` field directly (no `code` field, no MD5 fallback).
- Cross-entity references use `{kind, id, urlsafe}` objects — always extract via `_ref_id()`.
- Boolean property features come from `propertyfeaturevalue-N.json`; the `name` field is already denormalized. Pass the list to `build_sim_nao()` (core/characteristics_utils.py) for column 121 ("Outras características").
- Owner percentages: if all are zero, distribute `100/n` equally.
- Property `tipo` field = transaction type: `"SL"` (venda e locação), `"S"` (só venda), `"L"` (só locação) — derived from whether `sale_value` and/or `rental_value` are non-zero.
- `imobiliaria = "1"` on all `PersonRecord` and `PropertyRecord` emitted by this mapper.

### Registered mappers

| Nome | Formato | Exporta imóveis |
|------|---------|----------------|
| Arbo | XML | Sim |
| Code49 | XML | Sim |
| Imobi Brasil | XML | Sim |
| Imobzi | ZIP (JSONs) | Sim |
| Kenlo | ZIP (XLSX) | Sim |
| Msys Imob | SQL / ZIP | Não |
| Tec Imob | XLSX multi-aba | Sim |
| Univen | ZIP (XMLs) | Não |
| Vista CRM | ZIP (SQL) | Não |
