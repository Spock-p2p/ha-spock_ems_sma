"""Integración Spock EMS SMA (PV por Modbus; batería/PCC por Speedwire SHM2)"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# --- Modbus (solo para PV) ---
from pymodbus.client import ModbusTcpClient
from .compat_pymodbus import Endian
try:
    from pymodbus.payload import BinaryPayloadDecoder
except Exception:
    from .compat_payload import BinaryPayloadDecoder  # shim local si tu build lo necesita

# --- Speedwire / pysma (para batería y PCC) ---
import pysma

from .const import (
    DOMAIN,
    API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_PLANT_ID,
    # Tripower (PV por Modbus)
    CONF_PV_IP,
    CONF_PV_PORT,
    CONF_PV_SLAVE,
    # SHM2 (Speedwire)
    CONF_SHM_IP,
    CONF_SHM_GROUP,
    CONF_SHM_PASSWORD,
    # Varios
    DEFAULT_SCAN_INTERVAL_S,
    PLATFORMS,
    # Registros PV (Tripower)
    SMA_REG_PV_POWER,  # 30775 S32 FIX0
    # Keys
    KEY_BAT_SOC,
    KEY_BAT_POWER,
    KEY_PV_POWER,
    KEY_GRID_POWER,
    KEY_BAT_CAPACITY,
    KEY_BAT_CHARGE_ALLOWED,
    KEY_BAT_DISCHARGE_ALLOWED,
    KEY_TOTAL_GRID_OUTPUT,
)

_LOGGER = logging.getLogger(__name__)

# -------------------------
# Helpers Modbus (PV solo)
# -------------------------
def _mb_read(method, address: int, count: int, unit_id: int, **kwargs):
    """
    Llama a read_* probando unit=, luego slave=, y finalmente sin id de unidad.
    Evita posicionales porque algunas builds lo prohíben.
    """
    try:
        return method(address, count=count, unit=unit_id, **kwargs)
    except TypeError:
        try:
            return method(address, count=count, slave=unit_id, **kwargs)
        except TypeError:
            return method(address, count=count, **kwargs)


def _try_read_register_block(client, reg: int, count: int, unit_id: int):
    """
    Intenta leer reg con combinaciones típicas:
      * Input base 30001 y 30000
      * Holding base 40001 y 40000
    Devuelve (kind, addr, resp) con la primera lectura válida (no 0xFFFF...).
    """
    attempts = [
        ("input", reg - 30001),
        ("input", reg - 30000),
        ("holding", reg - 40001),
        ("holding", reg - 40000),
    ]
    last_exc = None
    for kind, addr in attempts:
        try:
            if addr < 0:
                continue
            if kind == "input":
                resp = _mb_read(client.read_input_registers, address=addr, count=count, unit_id=unit_id)
            else:
                resp = _mb_read(client.read_holding_registers, address=addr, count=count, unit_id=unit_id)
            if hasattr(resp, "isError") and resp.isError():
                continue
            regs = getattr(resp, "registers", None)
            if regs and not all((r & 0xFFFF) == 0xFFFF for r in regs):
                _LOGGER.debug("PV Modbus OK %s@%s unit=%s reg=%s -> %s", kind, addr, unit_id, reg, regs)
                return kind, addr, resp
        except Exception as e:
            last_exc = e
            continue
    raise ConnectionError(f"No PV regs at {reg} (last: {last_exc})")


# -------------------------
# Normalizadores (NaN SMA)
# -------------------------
INVALID_32U = {0xFFFFFFFF, 0x80000000}
INVALID_32S = {-1, -2147483648}


def _norm_u32(v: int) -> int | None:
    return None if v in INVALID_32U else v


def _norm_s32(v: int) -> int | None:
    return None if v in INVALID_32S else v


# -------------------------
# pysma keys (SHM2)
# -------------------------
# Lista de claves habituales en SHM2/Speedwire; se prueba en orden y
# se normaliza a ints.
PYSMA_KEYS = [
    ("Bat.SOC", "soc"),          # % SOC
    ("bat_soc", "soc"),
    ("Bat.Pwr", "bat_pwr"),      # W (positivo = descarga)
    ("bat_power", "bat_pwr"),
    ("GridMs.TotW", "grid_pwr"), # W (positivo = exportación a red)
    ("grid_power", "grid_pwr"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura la integración desde la entrada de configuración."""
    coordinator = SpockEnergyCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coordinator, "is_enabled": True}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _LOGGER.info("Spock EMS SMA: perfil mixto (PV Modbus Tripower + batería/PCC via SHM2 Speedwire).")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Descarga la entrada de configuración."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recarga la entrada de configuración al modificar opciones."""
    await hass.config_entries.async_reload(entry.entry_id)


class SpockEnergyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator que gestiona el ciclo de API unificado."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.config_entry = entry
        self.config = {**entry.data, **entry.options}
        self.api_token: str = self.config[CONF_API_TOKEN]
        self.plant_id: int = self.config[CONF_PLANT_ID]

        # Tripower (PV por Modbus)
        self.pv_ip: str = self.config[CONF_PV_IP]
        self.pv_port: int = self.config[CONF_PV_PORT]
        self.pv_slave: int = self.config[CONF_PV_SLAVE]

        # SHM2 (Speedwire pysma)
        self.shm_ip: str | None = self.config.get(CONF_SHM_IP)
        self.shm_group: str | None = self.config.get(CONF_SHM_GROUP)
        self.shm_password: str | None = self.config.get(CONF_SHM_PASSWORD)

        self._session = async_get_clientsession(hass)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_S),
        )

    # ---- Lecturas principales ----
    def _read_pv_modbus(self) -> int:
        """Lee potencia FV (W) del Tripower por Modbus (30775 S32)."""
        client = ModbusTcpClient(host=self.pv_ip, port=self.pv_port, timeout=5)
        try:
            client.connect()
            _, _, resp = _try_read_register_block(client, SMA_REG_PV_POWER, 2, self.pv_slave or 2)
            dec = BinaryPayloadDecoder.fromRegisters(resp.registers, byteorder=Endian.Big, wordorder=Endian.Little)
            raw = dec.decode_32bit_int()
            val = _norm_s32(raw) or 0
            return int(val)
        except Exception as e:
            _LOGGER.debug("PV Modbus read failed: %s", e)
            return 0
        finally:
            try:
                client.close()
            except Exception:
                pass

    async def _read_shm2_speedwire(self) -> dict[str, int]:
        """Lee SOC/bat_power/grid del SHM2 vía pysma. Devuelve ints (fallback 0)."""
        out = {"soc": 0, "bat_pwr": 0, "grid_pwr": 0}
        if not self.shm_ip:
            _LOGGER.debug("Sin shm_ip configurada: batería/PCC quedarán a 0.")
            return out

        sma = pysma.SMA(self._session, self.shm_ip, self.shm_password or "", self.shm_group)
        try:
            if not await sma.new_session():
                _LOGGER.debug("pysma: no se pudo iniciar sesión en SHM2 %s", self.shm_ip)
                return out

            # Algunas versiones de pysma usan read(k); si tu build usa get_values, adaptamos rápido.
            data: dict[str, Any] = {}
            for key, dest in PYSMA_KEYS:
                try:
                    val = await sma.read(key)
                    if val is not None:
                        data[dest] = val
                except Exception:
                    continue

            try:
                await sma.close_session()
            except Exception:
                pass

            # Normaliza a int
            if "soc" in data and data["soc"] is not None:
                try:
                    out["soc"] = int(float(data["soc"]))
                except Exception:
                    pass
            if "bat_pwr" in data and data["bat_pwr"] is not None:
                try:
                    out["bat_pwr"] = int(float(data["bat_pwr"]))
                except Exception:
                    pass
            if "grid_pwr" in data and data["grid_pwr"] is not None:
                try:
                    out["grid_pwr"] = int(float(data["grid_pwr"]))
                except Exception:
                    pass

            _LOGGER.debug("SHM2 Speedwire -> SOC=%s%%, BatPower=%sW, Grid=%sW", out["soc"], out["bat_pwr"], out["grid_pwr"])
            return out

        except Exception as e:
            _LOGGER.debug("pysma error: %s", e)
            try:
                await sma.close_session()
            except Exception:
                pass
            return out

    # ---- Bucle de actualización ----
    async def _async_update_data(self) -> dict[str, Any]:
        """Ciclo de actualización: PV (Modbus) + batería/PCC (Speedwire)."""
        # lee en paralelo: PV (executor) + SHM2 (async)
        pv_power = await self.hass.async_add_executor_job(self._read_pv_modbus)
        shm_vals = await self._read_shm2_speedwire()

        # Construye payload numérico
        telemetry = {
            KEY_PV_POWER: pv_power,
            KEY_BAT_SOC: shm_vals.get("soc", 0),
            KEY_BAT_POWER: shm_vals.get("bat_pwr", 0),
            KEY_GRID_POWER: shm_vals.get("grid_pwr", 0),
            KEY_BAT_CAPACITY: 0,                # no lo da SHM2 por defecto
            KEY_BAT_CHARGE_ALLOWED: True,       # placeholders
            KEY_BAT_DISCHARGE_ALLOWED: True,
            KEY_TOTAL_GRID_OUTPUT: 0,
        }

        # Envío a API Spock
        payload_api = {
            "plant_id": str(self.config[CONF_PLANT_ID]),
            "bat_soc": str(telemetry[KEY_BAT_SOC]),
            "bat_power": str(telemetry[KEY_BAT_POWER]),
            "pv_power": str(telemetry[KEY_PV_POWER]),
            "ongrid_power": str(telemetry[KEY_GRID_POWER]),
            "bat_charge_allowed": str(telemetry[KEY_BAT_CHARGE_ALLOWED]).lower(),
            "bat_discharge_allowed": str(telemetry[KEY_BAT_DISCHARGE_ALLOWED]).lower(),
            "bat_capacity": str(telemetry[KEY_BAT_CAPACITY]),
            "total_grid_output_energy": str(telemetry[KEY_TOTAL_GRID_OUTPUT]),
        }

        try:
            async with self._session.post(
                API_ENDPOINT,
                headers={"X-Auth-Token": self.config[CONF_API_TOKEN]},
                json=payload_api,
            ) as resp:
                if resp.status == 403:
                    raise UpdateFailed("API Token inválido (403)")
                if resp.status != 200:
                    txt = await resp.text()
                    _LOGGER.error("API error %s: %s", resp.status, txt)
                    raise UpdateFailed(f"Error de API (HTTP {resp.status})")
                return telemetry

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error("Error en el ciclo de actualización (API POST): %s", err)
            raise UpdateFailed(f"Error en el ciclo de actualización (API POST): {err}") from err
