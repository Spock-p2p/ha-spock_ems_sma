"""
Battery control helpers for SMA STP10.0-3SE-40 via Modbus TCP.

This module is used by the Spock EMS SMA integration to apply
setpoints returned by the Spock optimizer.

Main entry point:

    await async_apply_spock_operation(
        hass=hass,
        host=modbus_host,
        port=modbus_port,
        unit_id=modbus_unit_id,
        operation_mode=operation_mode,  # "charge" / "discharge" / "auto"
        action_w=action_w,              # watts, int or str, ignored for auto
    )

Rules:

- "charge": charge battery with +action_w watts
            (we write a NEGATIVE setpoint to 40149)
- "discharge": discharge battery with +action_w watts
               (we write a POSITIVE setpoint to 40149)
- "auto" or invalid/missing: go back to internal "auto" control
                             (40149 = 0, 40151 = 803)

If anything goes wrong inside (connection error, invalid power, etc.)
we fall back to AUTO mode as a safe default.
"""

from __future__ import annotations

import logging
from typing import Optional

from homeassistant.core import HomeAssistant

from pymodbus.client import ModbusTcpClient

_LOGGER = logging.getLogger(__name__)

# Modbus register addresses for STPxx-3SE-40
REG_BATT_POWER_SETPOINT = 40149  # S32, W, negative=charge, positive=discharge
REG_BATT_CONTROL_MODE = 40151    # U32, 802=manual/ext, 803=auto/internal

MODE_MANUAL = 802
MODE_AUTO = 803


# ----------------- low-level helpers (sync, run in executor) -----------------


def _split_u32(val: int) -> tuple[int, int]:
    """Split unsigned 32 bit int into two 16 bit registers (hi, lo)."""
    val &= 0xFFFFFFFF
    hi = (val >> 16) & 0xFFFF
    lo = val & 0xFFFF
    return hi, lo


def _split_s32(val: int) -> tuple[int, int]:
    """Split signed 32 bit int into two 16 bit registers (hi, lo)."""
    if val < 0:
        val = (val + (1 << 32)) & 0xFFFFFFFF
    return _split_u32(val)


def _write_u32(
    client: ModbusTcpClient,
    unit_id: int,
    address: int,
    value: int,
) -> None:
    hi, lo = _split_u32(value)
    regs = [hi, lo]
    res = client.write_registers(address, regs, device_id=unit_id)
    if res is None or res.isError():
        _LOGGER.warning(
            "SMA Modbus write_u32 failed at %s value=%s res=%s",
            address,
            value,
            res,
        )


def _write_s32(
    client: ModbusTcpClient,
    unit_id: int,
    address: int,
    value: int,
) -> None:
    hi, lo = _split_s32(value)
    regs = [hi, lo]
    res = client.write_registers(address, regs, device_id=unit_id)
    if res is None or res.isError():
        _LOGGER.warning(
            "SMA Modbus write_s32 failed at %s value=%s res=%s",
            address,
            value,
            res,
        )


def _set_manual_control_mode(
    client: ModbusTcpClient,
    unit_id: int,
) -> None:
    """
    Enable manual / external control for battery power.

    For STPxx-3SE-40 community reports:
      Reg 40151 = 802 -> manual/external control active.
    """
    _LOGGER.debug(
        "SMA battery: enabling manual control mode (40151=%s)", MODE_MANUAL
    )
    _write_u32(client, unit_id, REG_BATT_CONTROL_MODE, MODE_MANUAL)


def _set_auto_control_mode(
    client: ModbusTcpClient,
    unit_id: int,
) -> None:
    """
    Return to internal "auto" control:

      - clear external setpoint (40149 = 0 W)
      - set 40151 = 803 (auto/internal)
    """
    _LOGGER.debug("SMA battery: switching to auto mode")
    # 1) clear setpoint
    _write_s32(client, unit_id, REG_BATT_POWER_SETPOINT, 0)
    # 2) auto mode
    _write_u32(client, unit_id, REG_BATT_CONTROL_MODE, MODE_AUTO)


def _set_battery_setpoint(
    client: ModbusTcpClient,
    unit_id: int,
    setpoint_w: int,
) -> None:
    """
    Write signed W setpoint to 40149.

    Convention for STP10.0-3SE-40:

      setpoint > 0  -> discharge battery (inverter exports power)
      setpoint < 0  -> charge battery   (inverter imports power)
    """
    _LOGGER.debug(
        "SMA battery: writing setpoint %s W to 40149", setpoint_w
    )
    _write_s32(client, unit_id, REG_BATT_POWER_SETPOINT, setpoint_w)


def _apply_operation_sync(
    host: str,
    port: int,
    unit_id: int,
    operation_mode: str,
    power_w: int,
) -> bool:
    """
    Synchronous implementation that actually talks Modbus.

    Returns True if best-effort write was done, False on connection error.
    """
    client = ModbusTcpClient(host, port=port)
    _LOGGER.debug(
        "SMA battery: connecting Modbus host=%s port=%s unit_id=%s "
        "mode=%s power_w=%s",
        host,
        port,
        unit_id,
        operation_mode,
        power_w,
    )

    if not client.connect():
        _LOGGER.warning(
            "SMA battery: could not connect to Modbus device %s:%s",
            host,
            port,
        )
        return False

    try:
        mode = (operation_mode or "").lower()

        # Safety: anything unknown falls back to AUTO
        if mode not in ("charge", "discharge", "auto"):
            _LOGGER.warning(
                "SMA battery: unknown operation_mode=%s, falling back to auto",
                operation_mode,
            )
            _set_auto_control_mode(client, unit_id)
            return True

        # AUTO: always go back to internal control
        if mode == "auto":
            _LOGGER.info("SMA battery: setting AUTO mode")
            _set_auto_control_mode(client, unit_id)
            return True

        # For charge / discharge we need a positive power
        if power_w <= 0:
            _LOGGER.warning(
                "SMA battery: non-positive power %s for mode=%s, "
                "falling back to auto",
                power_w,
