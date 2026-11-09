from contextlib import asynccontextmanager

from app.bootstrap import create_app


@asynccontextmanager
async def isolated(app):
    yield


app = create_app()
# Registration preflight does not need model loading or AMQP consumers.
app.router.lifespan_context = isolated
