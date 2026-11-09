"""Run the published GoldenGate image on Modal as an on-demand public demo.

Deploy with:  modal deploy modal_app.py
Live at:      https://rgambhir777--goldengate.us-east.modal.run

The container starts on the first request (a few seconds: the demo releases are
baked into the image) and stops after SCALEDOWN_S idle seconds, which resets the
app to its seeded demo data. A single container keeps every visitor on the same
SQLite database. The app has no login, so anyone with the URL can use it,
including starting runs and editing gates and settings. No API keys are deployed:
the offline judge scores everything, so there is nothing to leak or spend.

Modal bills per second only while the container runs.
"""

import subprocess

import modal

# Tagged with the app version + git commit, never `latest`, so git shows exactly
# which build is deployed. Change it when you publish a new image (README "Docker").
IMAGE = "docker.io/nusoftinc/goldengate:1.0.0-cddeb2a"

PORT = 8000
SCALEDOWN_S = 600  # stop (and stop billing) after 10 minutes without requests
MAX_CONTAINERS = 1  # one copy: the SQLite database and background jobs live in one process

image = modal.Image.from_registry(IMAGE).env(
    {
        # The same values the Dockerfile sets, repeated so the app does not depend on
        # Modal honouring the image's ENV and WORKDIR.
        "GOLDENGATE_WORKSPACE": "/data",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    }
)

app = modal.App("goldengate")


@app.function(image=image, max_containers=MAX_CONTAINERS, scaledown_window=SCALEDOWN_S, timeout=600)
@modal.concurrent(max_inputs=100)  # one container serves many browser requests at once
@modal.web_server(PORT, startup_timeout=120, label="goldengate")
def serve() -> None:
    subprocess.Popen(
        ["python", "-m", "goldengate", "serve", "--host", "0.0.0.0", "--port", str(PORT), "--no-open"],
        cwd="/app",
    )
