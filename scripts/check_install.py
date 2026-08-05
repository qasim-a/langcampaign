#!/usr/bin/env python3
"""Run the non-destructive LangCampaign installation probe."""

from pathlib import Path
import runpy


namespace = runpy.run_path(str(Path(__file__).with_name("langcampaign_adapter.py")))
raise SystemExit(namespace["install_probe"](Path(__file__).with_name("langcampaign_adapter.py")))
