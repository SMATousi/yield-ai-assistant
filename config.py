import os
from pathlib import Path

DATA_DIR = Path(os.getenv("YIELD_DATA_DIR", "data/Data for Ali"))
AGGREGATE_CSV = DATA_DIR / "ExampleData_aggregate.csv"
LLM_MODEL = os.getenv("YIELD_LLM_MODEL", "ollama/qwen2.5:14b")
