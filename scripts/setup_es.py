"""
Create the Elasticsearch index for bird observations.
Safe to run multiple times — skips if the index already exists.

The .jina-clip-v2 inference endpoint is pre-deployed by Elastic and requires no setup.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import config
from app.es_client import get_client

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "embedding": {
                "type": "dense_vector",
                "dims": config.EMBEDDING_DIMS,
                "index": True,
                "similarity": "cosine",
            },
            "location": {"type": "geo_point"},
            "observed_on": {
                "type": "date",
                "format": "yyyy-MM-dd||yyyy-MM-dd HH:mm:ss",
            },
            "month": {"type": "integer"},
            "species_common": {"type": "keyword"},
            "species_scientific": {"type": "keyword"},
            "order": {"type": "keyword"},
            "family": {"type": "keyword"},
            "genus": {"type": "keyword"},
            "image_path": {"type": "keyword", "index": False},
            "category_id": {"type": "integer"},
            "image_id": {"type": "integer"},
            "rights_holder": {"type": "keyword"},
        }
    },
}


def main() -> None:
    es = get_client()
    print(f"Connecting to {config.ELASTICSEARCH_URL} …")
    info = es.info()
    print(f"[OK] Connected — cluster: {info['cluster_name']}, version: {info['version']['number']}")

    if es.indices.exists(index=config.INDEX_NAME):
        print(f"[OK] Index '{config.INDEX_NAME}' already exists — skipping")
    else:
        es.indices.create(index=config.INDEX_NAME, body=INDEX_MAPPING)
        print(f"[OK] Index '{config.INDEX_NAME}' created ({config.EMBEDDING_DIMS}-dim cosine vectors)")

    print("\nSetup complete. You can now run: python scripts/index_birds.py")


if __name__ == "__main__":
    main()
