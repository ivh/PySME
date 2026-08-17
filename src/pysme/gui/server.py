# -*- coding: utf-8 -*-
"""FastAPI server for PySME web GUI."""

import logging
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app():
    """Create and configure the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from fastapi.middleware.cors import CORSMiddleware

    from .api.routes import router, session

    @asynccontextmanager
    async def lifespan(app):
        # Start the computation worker now, so the first synthesis does not wait
        # for a fresh interpreter to import PySME.
        session.jobs.prewarm()
        yield
        session.jobs.shutdown()

    app = FastAPI(
        title="PySME GUI",
        description="Web interface for PySME spectral analysis",
        version="0.5.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    assets_dir = STATIC_DIR / "assets"
    index_file = STATIC_DIR / "index.html"

    if index_file.exists():
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/")
        async def serve_index():
            return FileResponse(index_file)

        @app.get("/{path:path}")
        async def serve_static(path: str):
            file_path = STATIC_DIR / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(index_file)
    else:
        @app.get("/")
        async def no_frontend():
            return {
                "message": "PySME GUI API is running. Frontend not built.",
                "hint": "Run 'npm run build' in src/pysme/gui/frontend/ to build the frontend",
                "docs": "/docs",
            }

    return app


def run_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True):
    """Run the PySME GUI server."""
    import uvicorn

    app = create_app()

    if open_browser:
        import threading
        import time

        def open_browser_delayed():
            time.sleep(1.0)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=open_browser_delayed, daemon=True).start()

    print(f"Starting PySME GUI at http://{host}:{port}")
    print("Press Ctrl+C to stop the server")

    # Bounded graceful shutdown: the progress and log streams never end on their
    # own, so Ctrl+C would otherwise wait for the browser to close them.
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",
        timeout_graceful_shutdown=5,
    )


def main():
    """Entry point for 'pysme gui' command."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Start the PySME web GUI server"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser automatically",
    )

    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
