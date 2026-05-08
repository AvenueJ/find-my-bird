import base64
import re
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
                    "location": {"lat": lat, "lon": lon},
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


def _parse_wkt_point(wkt: str) -> dict[str, float] | None:
    m = re.match(r"POINT\s*\(([+-]?\d+\.?\d*)\s+([+-]?\d+\.?\d*)\)", wkt)
    if m:
        return {"lon": float(m.group(1)), "lat": float(m.group(2))}
    return None


def _esql_to_dicts(resp: Any) -> list[dict]:
    columns = [c["name"] for c in resp.get("columns", [])]
    rows = []
    for values in resp.get("values", []):
        row = dict(zip(columns, values))
        if "location" in row and isinstance(row["location"], str):
            row["location"] = _parse_wkt_point(row["location"])
        rows.append(row)
    return rows


def search_esql(
    lat: float,
    lon: float,
    radius_km: float,
    month: int | None = None,
    limit: int = 50,
) -> list[dict]:
    month_filter = f"| WHERE month == {month}" if month else ""
    query = f"""
        FROM {config.INDEX_NAME}
        | WHERE location IS NOT NULL
        | WHERE ST_DISTANCE(location, ST_POINT({lon}, {lat})) <= {int(radius_km * 1000)}
        {month_filter}
        | KEEP species_common, species_scientific, family, order, image_path, observed_on, location
        | SORT observed_on DESC
        | LIMIT {limit}
    """
    es = get_client()
    resp = es.esql.query(body={"query": query})
    return _esql_to_dicts(resp)
