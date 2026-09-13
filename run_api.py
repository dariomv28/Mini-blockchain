"""Entrypoint script to run the PyChain API server."""

import uvicorn
from api.config import ApiConfig

if __name__ == "__main__":
    config = ApiConfig()
    print(f"Starting PyChain Web API on http://{config.api_host}:{config.api_port}")
    uvicorn.run(
        "api.app:app",
        host=config.api_host,
        port=config.api_port,
        reload=False,
        proxy_headers=False,
        ws_ping_interval=config.ws_ping_interval,
        ws_ping_timeout=config.ws_idle_timeout,
        ws_max_size=config.ws_max_message_bytes,
    )
