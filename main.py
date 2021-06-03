#! /usr/bin/env python3.9
import json
import math
import os
import statistics
from typing import Dict, List, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates("templates")
WEBSOCKET_HOST = os.environ.get("WEBSOCKET_HOST", "ws://localhost:8000")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.history: List[str] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        for message in self.history:
            await websocket.send_text(message)
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            self.history.append(message)
            await connection.send_text(message)


class FollowingStatus(ConnectionManager):
    def __init__(self):
        super().__init__()
        self._status: Dict[str, Optional[int]] = {}

    async def add_client(self, client_id: str):
        """ add a new client to the system """
        self._status[client_id] = 0

    async def remove_client(self, client_id: str):
        """ remove the client from the system """
        del self._status[client_id]

    async def update_value(self, client_id: str, value: int):
        """ update the following value for the user """
        self._status[client_id] = value
        await self.broadcast(self.json)

    def client_status(self, client_id: str) -> int:
        """ return the current users score """
        return self._status[client_id]

    @property
    def average(self) -> float:
        return sum(self._status.values()) / len(self._status)

    @property
    def json(self) -> str:
        return json.dumps({
            "detail": self._status,
            "mean": statistics.mean(self._status.values()),
            "median": math.floor(statistics.median_grouped(self._status.values())),
        })



CLIENTS = ConnectionManager()
FOLLOWING_STATUS = FollowingStatus()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    template = "index.html"
    context = {
        "request": request,
        "websocket_host": WEBSOCKET_HOST
    }
    return templates.TemplateResponse(template, context)


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await CLIENTS.connect(websocket)
    await FOLLOWING_STATUS.add_client(client_id) 
    try:
        while True:
            data: str = await websocket.receive_text()
            await CLIENTS.send_personal_message(f"You wrote: {data}", websocket)
            try:
                await FOLLOWING_STATUS.update_value(client_id, int(data))
                await CLIENTS.broadcast(f"Client #{client_id} adjusted their score to: {FOLLOWING_STATUS.client_status(client_id)}")
                await CLIENTS.broadcast(f"Following Value is {FOLLOWING_STATUS.average:.1f}")
            except ValueError:
                await CLIENTS.broadcast(f"Client #{client_id} says: {data}")
    except WebSocketDisconnect:
        CLIENTS.disconnect(websocket)
        await CLIENTS.broadcast(f"Client #{client_id} left the chat")
        await FOLLOWING_STATUS.remove_client(client_id)



@app.websocket("/mon/ws/")
async def monitor_endpoint(websocket: WebSocket):
    """ websocket for monitoring page """
    await FOLLOWING_STATUS.connect(websocket)
    try:
        while True:
            # handle the websocket
            data: str = await websocket.receive_text()
            print(data)
    except WebSocketDisconnect:
        await FOLLOWING_STATUS.disconnect(websocket)


@app.get("/mon/", response_class=HTMLResponse)
async def monitor(request: Request):
    template = "monitor.html"
    context = {
        "request": request,
        "websocket_host": WEBSOCKET_HOST,
    }
    return templates.TemplateResponse(template, context)