import base64
from typing import Any

from app import config
from app.es_client import get_client

_SOURCE_EXCLUDES = ["embedding"]


def _embed_image(image_bytes: bytes) -> list[float] | None:
    es = get_client()
    b64 = base64.b64encode(image_bytes).decode()
    try:
        resp = es.inference.inference(
            task_type="embedding",
            inference_id=config.EIS_ENDPOINT_ID,
            body={"input": b64},
        )
        results = resp.get("embeddings") or []
        if results:
            return results[0].get("embedding")
    except Exception as exc:
        raise RuntimeError(f"EIS embedding failed: {exc}") from exc
    return None


def _build_geo_month_filter(
    lat: float | None,
    lon: float | None,
    radius_km: float | None,
    month: int | None,
) -> dict | None:
    clauses: list[dict] = []
    if lat is not None and lon is not None and radius_km:
        clauses.append(
            {
                "geo_distance": {
                    "distance": f"{radius_km}km",
                    "inat_location": {"lat": lat, "lon": lon},
                }
            }
        )
    if month:
        clauses.append({"term": {"month": month}})
    if not clauses:
        return None
    return {"bool": {"must": clauses}}


def _format_hits(resp: Any) -> list[dict]:
    hits = []
    for h in resp["hits"]["hits"]:
        doc = h["_source"]
        doc["_score"] = h["_score"]
        hits.append(doc)
    return hits


def search_by_image(image_bytes: bytes, top_k: int = config.KNN_TOP_K) -> list[dict]:
    embedding = _embed_image(image_bytes)
    if embedding is None:
        return []
    es = get_client()
    resp = es.search(
        index=config.INDEX_NAME,
        knn={
            "field": "embedding",
            "query_vector": embedding,
            "k": top_k,
            "num_candidates": config.KNN_NUM_CANDIDATES,
        },
        source={"excludes": _SOURCE_EXCLUDES},
    )
    return _format_hits(resp)


def search_hybrid(
    image_bytes: bytes,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = None,
    month: int | None = None,
    top_k: int = config.KNN_TOP_K,
) -> list[dict]:
    embedding = _embed_image(image_bytes)
    if embedding is None:
        return []

    knn: dict = {
        "field": "embedding",
        "query_vector": embedding,
        "k": top_k,
        "num_candidates": config.KNN_NUM_CANDIDATES,
    }
    geo_month_filter = _build_geo_month_filter(lat, lon, radius_km, month)
    if geo_month_filter:
        knn["filter"] = geo_month_filter

    es = get_client()
    resp = es.search(
        index=config.INDEX_NAME,
        knn=knn,
        source={"excludes": _SOURCE_EXCLUDES},
    )
    return _format_hits(resp)



def search_esql(
    lat: float,
    lon: float,
    radius_km: float,
    month: int | None = None,
    limit: int = 50,
) -> list[dict]:
    must: list[dict] = [
        {"exists": {"field": "inat_location"}},
        {"geo_distance": {"distance": f"{radius_km}km", "inat_location": {"lat": lat, "lon": lon}}},
    ]
    if month:
        must.append({"term": {"month": month}})

    es = get_client()
    resp = es.search(
        index=config.INDEX_NAME,
        query={"bool": {"must": must}},
        sort=[{"inat_observed_on": {"order": "desc"}}],
        source={"excludes": ["embedding"]},
        size=limit,
    )
    return _format_hits(resp)
