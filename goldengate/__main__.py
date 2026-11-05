"""Allow ``python -m goldengate ...`` (used by the start scripts)."""

from goldengate.cli.main import app

app(prog_name="goldengate")
