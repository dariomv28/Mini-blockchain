from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from api.app import create_app
from api.config import ApiConfig

PASSWORD = "correct horse battery staple"


@asynccontextmanager
async def application(config=None):
    app = create_app(config or ApiConfig(node_port=0, node_db=None))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield app, client


async def csrf(client):
    response = await client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


async def register(client, name="alice"):
    response = await client.post("/api/v1/auth/register", headers=await csrf(client),
                                 json={"email": name + "@example.com", "username": name, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


async def login(client, name="alice", password=PASSWORD):
    return await client.post("/api/v1/auth/login", headers=await csrf(client),
                             json={"identifier": name, "password": password})


async def fund(node, address):
    from mining.miner import mine_block
    template = await node.create_mempool_block_template(address, max_transactions=0)
    block = mine_block(template, max_nonce=100_000)
    assert block is not None
    assert await node.accept_block(block)
    return block
