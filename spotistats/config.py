import os

# Feature flags and global settings
LOG_FILE = os.environ.get("SPOTISTATS_LOG_FILE", "spotistats.log")
WORKER_TIMEOUT = int(os.environ.get("WORKER_TIMEOUT", "15"))
APP_TITLE = os.environ.get("SPOTISTATS_APP_TITLE", "Spotistats")
