import anyio
from fastapi.testclient import TestClient as FastAPITestClient


class TestClient(FastAPITestClient):
    """
    Wrapper around FastAPI's TestClient that force-closes lifespan streams to
    avoid lingering ResourceWarning noise.
    """

    def __exit__(self, *args):
        result = super().__exit__(*args)
        for stream_name in ("stream_send", "stream_receive"):
            stream = getattr(self, stream_name, None)
            if stream:
                try:
                    anyio.run(stream.aclose)
                except Exception:
                    pass
        return result
