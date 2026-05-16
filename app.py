#!/usr/bin/env python3
# Compatibility shim — redirects to the restructured backend package.
from backend.main import app  # noqa: F401
from backend.jobs import jobs  # noqa: F401
