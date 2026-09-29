import os

# Prevent unauthenticated HuggingFace Hub network checks during test runs
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
