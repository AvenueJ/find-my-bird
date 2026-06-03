# Bird Nerd

Search bird observations by image similarity, location, and month using the [iNaturalist 2021 mini dataset](https://github.com/visipedia/inat_comp/tree/master/2021), [Jina Embeddings V5 Omni Small](https://jina.ai/embeddings/) embeddings via Elastic Inference Service, and Elasticsearch.

## Features

- **Visual Search** — upload a photo, get back the most visually similar birds in the dataset, optionally filtered by location and month
- **Explore by Location** — browse observations near any location using ES|QL geo queries, with results plotted on a map

## Prerequisites

- Python 3.11+
- [Elastic Cloud](https://cloud.elastic.co) deployment (8.x) — the `.jina-embeddings-v5-omni-small` model is hosted by Elastic, no external Jina API key needed
- [AWS CLI](https://aws.amazon.com/cli/) (for downloading the dataset)

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Description |
|---|---|
| `ELASTICSEARCH_URL` | Your Elastic Cloud endpoint, e.g. `https://my-deployment.es.io:443` |
| `ELASTICSEARCH_API_KEY` | API key from Kibana → Stack Management → API Keys |
| `INDEX_NAME` | Elasticsearch index name (default: `bird_observations`) |
| `DATA_DIR` | Absolute path to the directory that **directly contains** the species image folders (see step 3) |

### 3. Download the dataset

The iNaturalist 2021 mini dataset is hosted on a public S3 bucket (~15GB total, ~5GB for bird images).

```bash
cd data
aws s3 cp s3://ml-inat-competition-datasets/2021/train_mini.json.tar.gz . --no-sign-request
aws s3 cp s3://ml-inat-competition-datasets/2021/train_mini.tar.gz . --no-sign-request
tar -xzf train_mini.json.tar.gz
tar -xzf train_mini.tar.gz
```

This produces:
- `data/train_mini.json` — annotations with species, geo, and date info
- `data/train_mini/` — ~500k images organized into one folder per species

The indexer resolves each image as `DATA_DIR/<species_folder>/<file>`, so the species
folders must sit **directly** under `DATA_DIR`. Either point `DATA_DIR` at the
`train_mini` directory, or move the species folders up into `data/`:

```bash
mv data/train_mini/* data/
```

### 4. Create the Elasticsearch index

```bash
python scripts/setup_es.py
```

This creates the `bird_observations` index. The `.jina-embeddings-v5-omni-small`
inference endpoint is pre-deployed by Elastic, so there's nothing to create for it.
Safe to re-run — skips the index if it already exists.

### 5. Index the dataset

```bash
python scripts/index_birds.py
```

Filters the dataset to birds only (~74,300 images across 1,486 species), generates Jina Embeddings V5 Omni Small embeddings via EIS, and bulk-indexes everything into Elasticsearch. Progress is checkpointed to `indexed_ids.json` in the repo root (one file per `INDEX_NAME`) — you can interrupt with `Ctrl+C` and resume by re-running the same command.

Expected time: **3–6 hours** depending on network speed and EIS throughput.

### 6. Run the app

```bash
PYTHONPATH=. streamlit run app/main.py
```

Opens at `http://localhost:8501`.

## Project Structure

```
bird-nerd/
├── app/
│   ├── config.py       # env vars and constants
│   ├── es_client.py    # Elasticsearch client singleton
│   ├── search.py       # vector, hybrid, and ES|QL search functions
│   └── main.py         # Streamlit UI
├── scripts/
│   ├── setup_es.py     # create the ES index
│   └── index_birds.py  # parse dataset, embed images, bulk index
├── data/               # dataset lives here (gitignored)
├── indexed_ids.json    # indexing checkpoint, repo root (gitignored)
├── .env.example
├── requirements.txt
└── README.md
```
