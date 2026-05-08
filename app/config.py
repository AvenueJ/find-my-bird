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
EIS_ENDPOINT_ID: str = ".jina-clip-v2"

PROGRESS_FILE: Path = DATA_DIR / "indexed_ids.json"
