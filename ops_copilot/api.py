from fastapi import FastAPI

from ops_copilot import __version__

app = FastAPI(
    title="Rappi Ops Copilot API",
    version=__version__,
    description="Deterministic analytics API used by the n8n Rappi Ops Copilot workflow.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}

