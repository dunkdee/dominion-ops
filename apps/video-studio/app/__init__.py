"""Video Studio application package.

Declared explicitly so `app` resolves to this subproject rather than the
regular `app` package in OPS/radah-traffic-engine. A namespace package (no
__init__.py) always loses to a regular package found anywhere on sys.path,
which is why repository-wide collection previously imported the wrong `app`.
"""
