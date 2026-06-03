import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ELASTICSEARCH_URL: str = os.environ["ELASTICSEARCH_URL"]
ELASTICSEARCH_API_KEY: str = os.environ["ELASTICSEARCH_API_KEY"]

INDEX_NAME: str = os.getenv("INDEX_NAME", "bird_observations")

_data_dir_env = os.getenv("DATA_DIR")
DATA_DIR: Path = Path(_data_dir_env) if _data_dir_env else Path(__file__).parent.parent / "data"

EMBEDDING_DIMS: int = 1024
KNN_NUM_CANDIDATES: int = 100
KNN_TOP_K: int = 10
BULK_BATCH_SIZE: int = 100
EIS_ENDPOINT_ID: str = ".jina-embeddings-v5-omni-small"
EIS_MAX_BATCH_SIZE: int = 16

# Checkpoint file is derived from the index name so each index gets its own
# resumable progress file. Lives at the repo root (not under data/).
_REPO_ROOT: Path = Path(__file__).parent.parent
PROGRESS_FILE: Path = _REPO_ROOT / (
    "indexed_ids.json"
    if INDEX_NAME == "bird_observations"
    else f"indexed_ids_{INDEX_NAME}.json"
)

# Multimodal embedding input. A bare base64 string is treated as TEXT by the
# endpoint; an image must be wrapped in a content object. The server REQUIRES
# base64 values to be data URIs (data:{MIME};base64,...) — see InferenceString
# .validateDataURIFormat in elasticsearch — so this must stay True.
IMAGE_INPUT_USE_DATA_URI: bool = True


def build_image_input(b64: str) -> dict:
    """Build one multimodal `input` element for a base64-encoded image."""
    value = f"data:image/jpeg;base64,{b64}" if IMAGE_INPUT_USE_DATA_URI else b64
    return {"content": [{"type": "image", "format": "base64", "value": value}]}
