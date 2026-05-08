"""
Parse iNaturalist 2021 mini JSON, filter for birds (Aves), generate JINA-CLIP-V2
embeddings via Elastic Inference Service, and bulk-index into Elasticsearch.

Resumable: already-indexed image IDs are tracked in data/indexed_ids.json.
Run with: python scripts/index_birds.py
"""

import argparse
import base64
import json
import logging
import sys
import time
from pathlib import Path

from elasticsearch.helpers import bulk, BulkIndexError
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import config
from app.es_client import get_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

ANNOTATION_JSON = config.DATA_DIR / "train_mini.json"
IMAGE_ROOT = config.DATA_DIR
SLEEP_BETWEEN_CALLS = 0.15  # ~400 RPM, safely under Jina's 500 RPM limit


def load_bird_images(annotation_path: Path) -> list[dict]:
    log.info("Loading %s …", annotation_path)
    with open(annotation_path) as f:
        data = json.load(f)

    cat_by_id = {c["id"]: c for c in data["categories"]}
    ann_by_img = {a["image_id"]: a["category_id"] for a in data["annotations"]}

    bird_images = []
    for img in data["images"]:
        cat_id = ann_by_img.get(img["id"])
        if cat_id is None:
            continue
        cat = cat_by_id.get(cat_id)
        if cat and cat.get("class") == "Aves":
            bird_images.append({"img": img, "cat": cat})

    log.info("Found %d bird images across %d species", len(bird_images), len({e["cat"]["id"] for e in bird_images}))
    return bird_images


def load_checkpoint() -> set[int]:
    if config.PROGRESS_FILE.exists():
        ids = json.loads(config.PROGRESS_FILE.read_text())
        log.info("Resuming — %d images already indexed", len(ids))
        return set(ids)
    return set()


def save_checkpoint(indexed_ids: set[int]) -> None:
    config.PROGRESS_FILE.write_text(json.dumps(list(indexed_ids)))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def embed_image(es, image_bytes: bytes) -> list[float]:
    b64 = base64.b64encode(image_bytes).decode()
    resp = es.inference.inference(
        task_type="embedding",
        inference_id=config.EIS_ENDPOINT_ID,
        body={"input": b64},
    )
    results = resp.get("embeddings") or []
    if not results:
        raise ValueError("Empty embedding response from EIS")
    return results[0]["embedding"]


def build_doc(img: dict, cat: dict, embedding: list[float]) -> dict:
    date_str = (img.get("date") or "")[:10]
    month: int | None = None
    if len(date_str) >= 7:
        try:
            month = int(date_str[5:7])
        except ValueError:
            pass

    doc: dict = {
        "embedding": embedding,
        "species_common": cat.get("common_name", ""),
        "species_scientific": cat.get("name", ""),
        "order": cat.get("order", ""),
        "family": cat.get("family", ""),
        "genus": cat.get("genus", ""),
        "image_path": str(IMAGE_ROOT / cat["image_dir_name"] / Path(img["file_name"]).name),
        "category_id": cat["id"],
        "image_id": img["id"],
        "rights_holder": img.get("rights_holder", ""),
        "observed_on": date_str or None,
        "month": month,
    }

    lat = img.get("latitude")
    lon = img.get("longitude")
    if lat is not None and lon is not None:
        doc["location"] = {"lat": lat, "lon": lon}

    return doc


def generate_actions(batch: list[dict]):
    for doc in batch:
        yield {
            "_index": config.INDEX_NAME,
            "_id": doc["image_id"],
            "_source": {k: v for k, v in doc.items() if k != "image_id"},
        }


def flush_batch(es, batch: list[dict], indexed_ids: set[int]) -> int:
    try:
        successes, errors = bulk(es, generate_actions(batch), raise_on_error=True, stats_only=False)
    except BulkIndexError as exc:
        errors = exc.errors
        log.error("Bulk error (first 3): %s", errors[:3])
        successes = len(batch) - len(errors)

    for doc in batch:
        indexed_ids.add(doc["image_id"])
    save_checkpoint(indexed_ids)
    return successes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Index only this many images (for testing)")
    args = parser.parse_args()

    if not ANNOTATION_JSON.exists():
        log.error("Missing %s — download the dataset first (see README)", ANNOTATION_JSON)
        sys.exit(1)

    entries = load_bird_images(ANNOTATION_JSON)
    indexed_ids = load_checkpoint()
    remaining = [e for e in entries if e["img"]["id"] not in indexed_ids]
    if args.limit:
        remaining = remaining[: args.limit]
    log.info("%d images left to index", len(remaining))

    if not remaining:
        log.info("Nothing to do — all images already indexed.")
        return

    es = get_client()
    batch: list[dict] = []
    total_indexed = 0

    with tqdm(total=len(remaining), unit="img") as pbar:
        for entry in remaining:
            img = entry["img"]
            cat = entry["cat"]
            image_path = IMAGE_ROOT / cat["image_dir_name"] / Path(img["file_name"]).name

            pbar.set_postfix_str(cat.get("common_name", cat.get("name", "")))

            try:
                image_bytes = image_path.read_bytes()
            except OSError:
                log.warning("Missing file: %s", image_path)
                pbar.update(1)
                continue

            try:
                embedding = embed_image(es, image_bytes)
            except Exception as exc:
                log.warning("Embedding failed for image %d: %s", img["id"], exc)
                pbar.update(1)
                continue

            batch.append(build_doc(img, cat, embedding))
            pbar.update(1)
            time.sleep(SLEEP_BETWEEN_CALLS)

            if len(batch) >= config.BULK_BATCH_SIZE:
                n = flush_batch(es, batch, indexed_ids)
                total_indexed += n
                batch = []

    if batch:
        n = flush_batch(es, batch, indexed_ids)
        total_indexed += n

    log.info("Done. Indexed %d documents total.", total_indexed)


if __name__ == "__main__":
    main()
