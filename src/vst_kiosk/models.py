"""Pydantic models for all WebSocket message types.

Matches the VST Server protocol exactly. Uses discriminated union on the 'type' field.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# --- Room and Unit models used in config ---

class RoomState(BaseModel):
    room_id: int
    name: str
    floor: str
    device_id: str = ""
    nuc_status: Literal["online", "offline", "unregistered", "no_device", "paused", "calibration", "deactivated"] = "no_device"
    active_alert: str | None = None
    monitoring_type: Literal["bed", "chair"] = "bed"


class UnitState(BaseModel):
    unit_id: int
    unit_name: str
    branch: str = ""
    rooms: list[RoomState] = []


# --- Server -> Kiosk messages ---

class ConfigMessage(BaseModel):
    type: Literal["config"]
    kiosk_id: str = ""
    facility: str = ""
    synced_at: str = ""
    units: list[UnitState] = []


class AlertMessage(BaseModel):
    type: Literal["alert"]
    alert_id: str
    room_id: int
    room_name: str = ""
    floor: str = ""
    unit_name: str = ""
    branch: str = ""
    facility: str = ""
    device_id: str = ""
    event_type: str = ""
    alert_level: Literal["highRisk", "lowRisk"] = "highRisk"
    event_time: str = ""


class AlertClearedMessage(BaseModel):
    type: Literal["alert_cleared"]
    alert_id: str
    device_id: str = ""
    room_id: int
    room_name: str = ""
    unit_name: str = ""


class DeviceOfflineMessage(BaseModel):
    type: Literal["device_offline"]
    device_id: str = ""
    room_id: int
    room_name: str = ""
    unit_name: str = ""


class DeviceOnlineMessage(BaseModel):
    type: Literal["device_online"]
    device_id: str = ""
    room_id: int
    room_name: str = ""
    unit_name: str = ""


class KeyboardEventMessage(BaseModel):
    """Nurse paused/resumed/changed mode on NUC."""
    type: Literal["keyboard_event"]
    device_id: str = ""
    room_id: int
    room_name: str = ""
    unit_name: str = ""
    event_status: str = ""
    monitoring_type: str = ""
    nuc_status: str = ""


class NurseArrivedMessage(BaseModel):
    """NUC detected second person near patient."""
    type: Literal["nurse_arrived"]
    device_id: str = ""
    room_id: int
    room_name: str = ""
    unit_name: str = ""


class RoomAddedMessage(BaseModel):
    type: Literal["room_added"]
    room_id: int
    room_name: str = ""
    unit_name: str = ""


class RoomRemovedMessage(BaseModel):
    type: Literal["room_removed"]
    room_id: int
    room_name: str = ""
    unit_name: str = ""


class ConnectionStatusMessage(BaseModel):
    """Internal message sent from backend to browser to indicate upstream connection state."""
    type: Literal["connection_status"]
    connected: bool
    message: str = ""


# --- Kiosk -> Server messages ---

class SyncRequestMessage(BaseModel):
    type: Literal["sync_request"]


class AckMessage(BaseModel):
    type: Literal["ack"]
    alert_id: str


# --- Discriminated union for parsing ---

ServerMessage = Annotated[
    Union[
        ConfigMessage,
        AlertMessage,
        AlertClearedMessage,
        DeviceOfflineMessage,
        DeviceOnlineMessage,
        KeyboardEventMessage,
        NurseArrivedMessage,
        RoomAddedMessage,
        RoomRemovedMessage,
    ],
    Field(discriminator="type"),
]

BrowserMessage = Annotated[
    Union[AckMessage, SyncRequestMessage],
    Field(discriminator="type"),
]


def parse_server_message(data: dict) -> ServerMessage:
    """Parse a raw dict from the server into a typed message."""
    from pydantic import TypeAdapter
    adapter = TypeAdapter(ServerMessage)
    return adapter.validate_python(data)


def parse_browser_message(data: dict) -> BrowserMessage:
    """Parse a raw dict from the browser into a typed message."""
    from pydantic import TypeAdapter
    adapter = TypeAdapter(BrowserMessage)
    return adapter.validate_python(data)
