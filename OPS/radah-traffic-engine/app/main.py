from pathlib import Path

# Repository transport loader: the production source is split into reviewable
# fragments to preserve the exact tested v2.2 module during connector staging.
_base = Path(__file__).resolve().parent / "_main_source"
_source = "".join(((_base / f"part{i:02}.pyfrag").read_text(encoding="utf-8")) for i in range(5))
exec(compile(_source, str(Path(__file__).resolve()), "exec"), globals(), globals())
