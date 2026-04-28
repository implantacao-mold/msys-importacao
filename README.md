# Migração de Dados — Msys Imob

Ferramenta desktop (interface web local) para converter backups de sistemas imobiliários para o formato de importação do **Msys Imob**.

---

## Requisitos

- Python 3.11 ou superior
- pip

## Instalação

```bash
pip install -r requirements.txt
```

## Execução

```bash
python main.py
```

O navegador abre automaticamente em `http://127.0.0.1:5000`.

---

## Como usar

### 1. Selecione o sistema de origem

Escolha na lista o sistema do qual veio o arquivo de backup. Sistemas suportados:

| Sistema | Formato do arquivo |
|---------|-------------------|
| Arbo | `.xml` |
| Code49 | `.xml` |
| Imobi Brasil | `.xml` |
| Imobzi | `.zip` (exportação completa com JSONs) |
| Kenlo | `.zip` (com planilhas XLSX) |
| Msys Imob | `.sql` ou `.zip` |
| Tec Imob | `.xlsx` (múltiplas abas) |
| Univen | `.zip` (com XMLs) |
| Vista CRM | `.zip` (com SQL) |

### 2. Informe os dados da imobiliária

Preencha o **CPF/CNPJ** e o **nome** da imobiliária. Esses dados são usados como fallback quando o backup não contém informações de proprietário ou captador do imóvel.

### 3. Escolha o destino da exportação

- **Baixar ZIP**: gera um arquivo ZIP para download direto no navegador.
- **Salvar em pasta**: informa um caminho local e os arquivos CSV são gravados diretamente nele.

### 4. Selecione o arquivo e exporte

Clique em **Exportar** e aguarde. O progresso é exibido em tela.

---

## Arquivos gerados

Os CSVs são gerados no encoding **cp1252** com separador **`;`**, prontos para importação no Msys Imob.

### Pessoas (`PERSON/`)

| Arquivo | Conteúdo |
|---------|----------|
| `PERSON.csv` | Cadastro de pessoas (proprietários, locatários, compradores, fiadores, colaboradores) |
| `EMAIL.csv` | Endereços de e-mail vinculados às pessoas |
| `PHONE.csv` | Telefones vinculados às pessoas |

### Imóveis (`PROPERTY/`) — apenas sistemas que exportam imóveis

| Arquivo | Conteúdo |
|---------|----------|
| `PROPERTY.csv` | Dados cadastrais do imóvel (137 colunas) |
| `PROPERTY_OWNER.csv` | Proprietários do imóvel |
| `PROPERTY_OWNER_FAVORED.csv` | Favorecidos/beneficiários do pagamento |
| `PROPERTY_CAPTIVATOR.csv` | Captadores do imóvel |
| `PROPERTY_IPTU.csv` | Registros de IPTU |

---

## Regras de exportação

### Endereço
- Bairro ou logradouro em branco → preenchido com `Não Informado`
- Número em branco → preenchido com `0`
- Número com letras → letras movidas para o complemento (`Nº <original>`), campo zerado

### Subcategoria
Mapeamento automático a partir do tipo/subtipo do imóvel. Quando não há correspondência, usa-se `7` (Casa Padrão) como padrão.

### Características (coluna DQ)
Apenas características com `flg_load_in_combobox = 1` na lista oficial do Msys são exportadas. O mapeamento é feito em tempo de execução por correspondência fuzzy — nomes não reconhecidos são ignorados.

### Proprietário / captador sem dados
Quando o backup não informa proprietário ou captador, os campos são preenchidos com o CPF/CNPJ e nome da imobiliária informados na tela.

---

## Testes

```bash
pytest tests/ -q
```

---

## Estrutura do projeto

```
core/               Módulos compartilhados (engine, exporter, records, utils)
  caracteristicas.py    Lista oficial de características do Msys (combobox)
  subcategorias.py      Lista oficial de subcategorias do Msys
  characteristics_utils.py  Mapeamento fuzzy de características
  property_records.py   Dataclasses e normalize_address()
  engine.py             Orquestra carga de arquivo + execução do mapper
  exporter.py           Grava os CSVs de pessoas
  property_exporter.py  Grava os CSVs de imóveis

mappers/            Um arquivo por sistema de origem
  _template.py          Ponto de partida para novos mappers

gui/                Interface web (Flask + HTML/JS)
tests/              Testes automatizados (pytest)
main.py             Ponto de entrada
```

---

## Adicionando suporte a um novo sistema

1. Copie `mappers/_template.py` → `mappers/<sistema>.py`
2. Defina `NAME`, `EXTENSIONS`, `DESCRIPTION`
3. Implemente `extract(data)` (arquivo único) ou `extract_zip(files: dict)` (ZIP)
4. Registre o mapper em `mappers/__init__.py` dentro de `build_engine()`

Para exportar imóveis, popule um `PropertyExtractionResult` (ver `core/property_records.py`) e atribua a `result.property_result`.
