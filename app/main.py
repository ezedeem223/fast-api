from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from . import models
from .database import engine
from .routers import (
    post,
    user,
    auth,
    vote,
    comment,
    follow,
    block,
    admin_dashboard,
    oauth,
    search,
    message,
    community,
    p2fa,
)
from .config import settings
from .notifications import (
    ConnectionManager,
    send_real_time_notification,
)

# from hvac import Client

# Initialize Vault client
# vault_client = Client(url="http://127.0.0.1:8200", token=settings.vault_token)
# secrets = (
#     vault_client.secrets.kv.v2.read_secret_version(path="fastapi")
#     .get("data")
#     .get("data")
# )

# Update settings with secrets from Vault
# settings.database_password = secrets["DATABASE_PASSWORD"]
# settings.secret_key = secrets["SECRET_KEY"]

app = FastAPI()

# إعدادات CORS
origins = ["https://www.google.com"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(post.router)
app.include_router(user.router)
app.include_router(auth.router)
app.include_router(vote.router)
app.include_router(comment.router)
app.include_router(follow.router)
app.include_router(block.router)
app.include_router(admin_dashboard.router)
app.include_router(oauth.router)
app.include_router(search.router)
app.include_router(message.router)
app.include_router(community.router)
app.include_router(p2fa.router)

manager = ConnectionManager()


@app.get("/")
def read_root():
    return {"message": "Hello, World!"}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await send_real_time_notification(websocket, user_id, data)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        print(f"Client #{user_id} disconnected")
