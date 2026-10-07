"""
BDX AI - optional convenience launcher.
Equivalent to running server.py directly; kept so users can run
`python app.py` from the share directory during development.
"""
import os
import runpy

os.environ.setdefault("BDXAI_PORT", "8080")
runpy.run_path(os.path.join(os.path.dirname(__file__), "server.py"), run_name="__main__")
