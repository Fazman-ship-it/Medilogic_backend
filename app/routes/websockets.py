from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.dependencies import get_current_user_ws, get_db
from app import models
from app.models import DriverLocationHistory
from sqlalchemy.orm import Session
from datetime import datetime
from starlette.websockets import WebSocketState
from broadcaster import Broadcast
from typing import Dict, List

router = APIRouter()
broadcast = Broadcast("memory://")

# Store active WebSocket connections by org
active_connections: Dict[int, List[WebSocket]] = {}
# Store tracking connections per driver
connected_clients: Dict[int, List[WebSocket]] = {}  # key: driver_id


# Broadcast system startup/shutdown
@router.on_event("startup")
async def startup():
    await broadcast.connect()

@router.on_event("shutdown")
async def shutdown():
    await broadcast.disconnect()


# Internal function to manage org-wide sockets
async def connect(websocket: WebSocket, org_id: int):
    await websocket.accept()
    if org_id not in active_connections:
        active_connections[org_id] = []
    active_connections[org_id].append(websocket)

def disconnect(websocket: WebSocket, org_id: int):
    if org_id in active_connections and websocket in active_connections[org_id]:
        active_connections[org_id].remove(websocket)


@router.websocket("/ws/location")
async def websocket_location(
    websocket: WebSocket,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_ws)
):
    if current_user.role != "driver":
        await websocket.close(code=1008)
        return

    await connect(websocket, current_user.org_id)

    try:
        while True:
            data = await websocket.receive_json()

            latitude = data.get("latitude")
            longitude = data.get("longitude")

            if latitude is not None and longitude is not None:
                current_user.latitude = latitude
                current_user.longitude = longitude
                db.commit()

                # Log location history
                location_log = DriverLocationHistory(
                    driver_id=current_user.id,
                    org_id=current_user.org_id,
                    latitude=latitude,
                    longitude=longitude,
                    timestamp=datetime.utcnow()
                )
                db.add(location_log)
                db.commit()

                payload = {
                    "driver_id": current_user.id,
                    "name": current_user.name,
                    "latitude": latitude,
                    "longitude": longitude
                }

                # Broadcast to dashboard clients in same org
                for ws in active_connections.get(current_user.org_id, []):
                    if ws.application_state == WebSocketState.CONNECTED:
                        await ws.send_json(payload)

                # ✅ Broadcast to real-time tracking subscribers
                await broadcast_location_update(current_user.id, payload)

    except WebSocketDisconnect:
        disconnect(websocket, current_user.org_id)


@router.websocket("/ws/dashboard")
async def websocket_dashboard(
    websocket: WebSocket,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_ws)
):
    if current_user.role not in ["admin", "client"]:
        await websocket.close(code=1008)
        return

    await connect(websocket, current_user.org_id)

    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        disconnect(websocket, current_user.org_id)


@router.websocket("/ws/driver/{driver_id}")
async def realtime_driver_tracking(
    websocket: WebSocket,
    driver_id: int,
    user: models.User = Depends(get_current_user_ws)
):
    await websocket.accept()

    # Authorization check
    if user.role not in ["admin", "client"] and user.id != driver_id:
        await websocket.close(code=1008)
        return

    if user.org_id != (
        user.id if user.role == "driver" else
        (await get_driver_org(driver_id))
    ):
        await websocket.close(code=1008)
        return

    # Register connection
    if driver_id not in connected_clients:
        connected_clients[driver_id] = []
    connected_clients[driver_id].append(websocket)

    try:
        async with broadcast.subscribe(channel=f"driver:{driver_id}") as subscriber:
            async for event in subscriber:
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_json(event.message)
    except WebSocketDisconnect:
        pass
    finally:
        connected_clients[driver_id].remove(websocket)


async def broadcast_location_update(driver_id: int, location_data: dict):
    await broadcast.publish(
        channel=f"driver:{driver_id}",
        message=location_data
    )

async def get_driver_org(driver_id: int) -> int:
    from app.database import SessionLocal
    db = SessionLocal()
    driver = db.query(models.User).filter(models.User.id == driver_id).first()
    return driver.org_id if driver else -1