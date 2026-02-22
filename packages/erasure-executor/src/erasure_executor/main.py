from __future__ import annotations

import os
from pathlib import Path

from erasure_executor.api import build_app
from erasure_executor.config import load_config
from erasure_executor.db.base import Base
from erasure_executor.db.session import make_session_factory
from erasure_executor.engine.bootstrap import write_startup_artifact
from erasure_executor.engine.runner import Runner
from erasure_executor.logging import configure_logging

config_path = Path(os.environ.get("ERASURE_EXECUTOR_CONFIG", "/etc/erasure-executor/config.yaml"))
config = load_config(config_path)

configure_logging(redact=config.pii.log_redaction)

session_factory, engine = make_session_factory(config.database_url)
if os.getenv("ERASURE_EXECUTOR_AUTO_CREATE_SCHEMA", "false").lower() == "true":
    Base.metadata.create_all(bind=engine)

write_startup_artifact(config)
runner = Runner(session_factory, config)

app = build_app(config, session_factory, runner)
