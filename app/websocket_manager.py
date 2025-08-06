# app/websocket_manager.py

from typing import Dict, List
from fastapi import WebSocket
from uuid import UUID

class ConnectionManager:
    def __init__(self):
        # Store connections by organization_id
        self.active_admins: Dict[UUID, List[WebSocket]] = {}  # org_id → list of admin sockets
        self.active_drivers: Dict[UUID, WebSocket] = {}       # user_id → driver socket

    async def connect_admin(self, websocket: WebSocket, organization_id: UUID):
        await websocket.accept()
        if organization_id not in self.active_admins:
            self.active_admins[organization_id] = []
        self.active_admins[organization_id].append(websocket)

    async def connect_driver(self, websocket: WebSocket, user_id: UUID):
        await websocket.accept()
        self.active_drivers[user_id] = websocket

    def disconnect_admin(self, websocket: WebSocket, organization_id: UUID):
        if organization_id in self.active_admins:
            self.active_admins[organization_id].remove(websocket)
            if not self.active_admins[organization_id]:
                del self.active_admins[organization_id]

    def disconnect_driver(self, user_id: UUID):
        if user_id in self.active_drivers:
            del self.active_drivers[user_id]

    async def broadcast_to_admins(self, organization_id: UUID, message: dict):
        if organization_id in self.active_admins:
            for admin_ws in self.active_admins[organization_id]:
                await admin_ws.send_json(message)

# Create one global instance
connection_manager = ConnectionManager()