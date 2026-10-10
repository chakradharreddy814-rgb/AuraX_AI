"""
gunicorn_config.py — production server settings for AuraX AI.

Run with:  gunicorn -c gunicorn_config.py app:app
(If a config value is also set as an env var, the env var wins.)
"""

import os
import multiprocessing

# Network
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:5000")

# Workers: default 2 x CPU cores + 1 (I/O-bound workload)
workers = int(os.getenv("GUNICORN_WORKERS", str(multiprocessing.cpu_count() * 2 + 1)))
threads = int(os.getenv("GUNICORN_THREADS", "2"))

# Gemini calls can be slow — allow long requests
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30

# Logging
accesslog = "-"
errorlog = "-"

# Reload only in development
reload = os.getenv("FLASK_ENV", "development") == "development"
