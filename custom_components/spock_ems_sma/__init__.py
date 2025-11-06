"""Integración Spock EMS SMA (Modbus)"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# --- Imports de Modbus (compatibles) ---
from pymodbus.client import ModbusTcpClient
from .compat_pymodbus import Endian

try:
    # PyModbus < 3.11
    from pymodbus.payload import BinaryPayloadDecoder, BinaryPayloadBuilder
except Exception:
    # Shim local si payload no existe en tu build
    from .compat_payload import BinaryPayloadDecoder, BinaryPayloadBuilder
# --- FIN ---

# --- CAMBIOS: Imports añadidos ---
import pysma
from .const import (
    DOMAIN,
    API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_PLANT_ID,
    CONF_BATTERY_IP,
    CONF_BATTERY_PORT,
    CONF_BATTERY_SLAVE,
    CONF_PV_IP,
    CONF_PV_PORT,
    CONF_PV_SLAVE,
    CONF_SHM_IP,
    CONF_SHM_GROUP,
    CONF_SHM_PASSWORD,
    DEFAULT_SCAN_INTERVAL_S,
    PLATFORMS,
    # Registros
    SMA_REG_BAT_POWER,
    SMA_REG_BAT_SOC,
    SMA_REG_BAT_CAPACITY,
    SMA_REG_GRID_POWER,
    SMA_REG_PV_POWER,
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
# --- FIN CAMBIOS ---

_LOGGER = logging.getLogger(__name__)

# ===============================
# Compat helpers para PyModbus (KW-only, sin posicionales)
# ===============================

def _mb_read(method, address: int, count: int, unit_id: int, **kwargs):
    """
    Llama a read_* probando primero unit=, luego slave= y, si el cliente
    no acepta id de unidad, sin él. Nunca usa argumentos posicionales
    para 'count' ni para la unidad, porque hay builds que los prohíben.
    """
    # 1) PyModbus 3.x frecuentes (count kw-only + unit)
    try:
        return method(address, count=count, unit=unit_id, **kwargs)
    except TypeError:
        # 2) PyModbus 2.x (count kw-only + slave)
        try:
            return method(address, count=count, slave=unit_id, **kwargs)
        except TypeError:
            # 3) Algunos clientes ignoran el id de unidad: probar sin él
            return method(address, count=count, **kwargs)


def _mb_write_single(method, address: int, value: int, unit_id: int, **kwargs):
    # 1) unit=
    try:
        return method(address, value=value, unit=unit_id, **kwargs)
    except TypeError:
        # 2) slave=
        try:
            return method(address, value=value, slave=unit_id, **kwargs)
        except TypeError:
            # 3) sin id de unidad
            return method(address, value=value, **kwargs)


def _mb_write_multi(method, address: int, values, unit_id: int, **kwargs):
    # 1) unit=
    try:
        return method(address, values=values, unit=unit_id, **kwargs)
    except TypeError:
        # 2) slave=
        try:
            return method(address, values=values, slave=unit_id, **kwargs)
        except TypeError:
            # 3) sin id de unidad
            return method(address, values=values, **kwargs)


def _try_read_register_block(client, reg: int, count: int, unit_id: int):
    """
    Intenta leer 'reg' con combinaciones típicas:
    - Holding con base 40001 y 40000
    - Input con base 30001 y 30000
    Devuelve la primera respuesta válida (sin isError).
    """
    attempts = [
        ("holding", reg - 40001),
        ("holding", reg - 40000),
        ("input", reg - 30001),
        ("input", reg - 30000),
    ]

    for kind, addr in attempts:
        try:
            if addr < 0:
                continue
            if kind == "holding":
                resp = _mb_read(
                    client.read_holding_registers,
                    address=addr,
                    count=count,
                    unit_id=unit_id,
                )
            else:
                resp = _mb_read(
                    client.read_input_registers,
                    address=addr,
                    count=count,
                    unit_id=unit_id,
                )

            # Algunas builds devuelven objeto con isError(); otras lanzan excepción.
            if hasattr(resp, "isError") and resp.isError():
                _LOGGER.debug(
                    "Intento %s@%s (unit=%s) devolvió excepción Modbus: %s",
                    kind,
                    addr,
                    unit_id,
                    resp,
                )
                continue

            _LOGGER.debug(
                "Lectura OK con %s@%s (unit=%s), reg lógico %s, count=%s",
                kind,
                addr,
                unit_id,
                reg,
                count,
            )
            return kind, addr, resp
        except Exception as e:
            _LOGGER.debug(
                "Intento %s@%s (unit=%s) falló: %s", kind, addr, unit_id, e
            )
            continue

    raise ConnectionError(
        f"No se pudo leer reg {reg} count {count} (unit {unit_id}) "
        f"con ninguna combinación de función/offset estándar."
    )

# --- Normalización de valores SMA ---
INVALID_16 = {0xFFFF}
INVALID_32U = {0xFFFFFFFF, 0x80000000}
INVALID_32S = {-1, -2147483648}


def _norm_u16(v: int) -> int | None:
    return None if v in INVALID_16 else v


def _norm_u32(v: int) -> int | None:
    return None if v in INVALID_32U else v


def _norm_s32(v: int) -> int | None:
    return None if v in INVALID_32S else v


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura la integración desde la entrada de configuración."""
    coordinator = SpockEnergyCoordinator(hass, entry)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "is_enabled": True,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
        "Spock EMS SMA: Configuración cargada. El ciclo se iniciará automáticamente."
    )
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
        # Inicializa el coordinador.
        self.config_entry = entry
        self.config = {**entry.data, **entry.options}
        self.api_token: str = self.config[CONF_API_TOKEN]
        self.plant_id: int = self.config[CONF_PLANT_ID]

        self.battery_ip: str = self.config[CONF_BATTERY_IP]
        self.battery_port: int = self.config[CONF_BATTERY_PORT]
        self.battery_slave: int = self.config[CONF_BATTERY_SLAVE]

        self.pv_ip: str = self.config[CONF_PV_IP]
        self.pv_port: int = self.config[CONF_PV_PORT]
        self.pv_slave: int = self.config[CONF_PV_SLAVE]

        # --- Config SHM ---
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

    # --- Lectura Modbus: devuelve NÚMEROS ---
    def _read_sma_telemetry(self) -> dict[str, Any] | None:
        """[FUNCIÓN SÍNCRONA] Lee los registros Modbus de los inversores SMA."""
        _LOGGER.debug("Iniciando lectura Modbus SMA...")

        battery_client = ModbusTcpClient(
            host=self.battery_ip, port=self.battery_port, timeout=5
        )
        pv_client = ModbusTcpClient(host=self.pv_ip, port=self.pv_port, timeout=5)

        try:
            bat_soc = 0
            bat_power = 0
            pv_power = 0
            ongrid_power = 0
            bat_capacity = 0
            bat_charge_allowed = True
            bat_discharge_allowed = True

            # --- 1. Leer Inversor de Batería (Obligatorio) ---
            _LOGGER.debug("Conectando a Inversor Batería: %s", self.battery_ip)
            battery_client.connect()

            kind_bat, addr_bat, bat_regs = _try_read_register_block(
                battery_client, SMA_REG_BAT_POWER, 8, self.battery_slave
            )

            # --- DIAGNÓSTICO: dump + decodificaciones alternativas ---
            _LOGGER.debug("BAT regs raw: %s", getattr(bat_regs, "registers", None))
            
            def _try_decode32(regs, byteorder, wordorder):
                try:
                    dec = BinaryPayloadDecoder.fromRegisters(regs, byteorder=byteorder, wordorder=wordorder)
                    v1 = dec.decode_32bit_int()
                    v2 = dec.decode_32bit_uint()
                    v3 = BinaryPayloadDecoder.fromRegisters(regs[2:4], byteorder=byteorder, wordorder=wordorder).decode_32bit_uint()
                    v4 = BinaryPayloadDecoder.fromRegisters(regs[6:8], byteorder=byteorder, wordorder=wordorder).decode_32bit_uint()
                    return v1, v2, v3, v4
                except Exception as e:
                    return f"error:{e}", None, None, None
            
            for bo, wo, tag in [
                (Endian.Big, Endian.Big, "BB"),
                (Endian.Big, Endian.Little, "BL"),
                (Endian.Little, Endian.Big, "LB"),
                (Endian.Little, Endian.Little, "LL"),
            ]:
                p, soc32, soc32_alt, cap = _try_decode32(bat_regs.registers, bo, wo)
                _LOGGER.debug("BAT decode %s -> P=%s, SOC32=%s, SOC32_alt=%s, CAP=%s", tag, p, soc32, soc32_alt, cap)
            
            # SOC u16 directo (por si ese es el bueno) y con posible escala 0.1
            try:
                _LOGGER.debug("SOC16 regs raw: %s", getattr(soc16_regs, "registers", None))
            except NameError:
                # leer por si no se ha leído aún
                _, _, soc16_regs = _try_read_register_block(battery_client, SMA_REG_BAT_SOC, 1, self.battery_slave)
                _LOGGER.debug("SOC16 regs raw: %s", getattr(soc16_regs, "registers", None))
            
            try:
                dec_soc16 = BinaryPayloadDecoder.fromRegisters(soc16_regs.registers, byteorder=Endian.Big)
                soc16_val = dec_soc16.decode_16bit_uint()
                _LOGGER.debug("SOC16 u16=%s, u16_scaled(0.1)=%s%%", soc16_val, soc16_val / 10.0)
            except Exception as e:
                _LOGGER.debug("SOC16 decode error: %s", e)
            # --- FIN DIAGNÓSTICO ---
            

            decoder_bat = BinaryPayloadDecoder.fromRegisters(
                bat_regs.registers, byteorder=Endian.Big, wordorder=Endian.Little
            )
            # orden esperada: INT32 potencia, UINT32 SOC, skip 4 bytes, UINT32 capacity
            bat_power_raw = decoder_bat.decode_32bit_int()
            bat_soc_raw = decoder_bat.decode_32bit_uint()
            decoder_bat.skip_bytes(4)
            bat_capacity_raw = decoder_bat.decode_32bit_uint()

            bat_power = _norm_s32(bat_power_raw)
            bat_soc = _norm_u32(bat_soc_raw)
            bat_capacity = _norm_u32(bat_capacity_raw)

            # Si el SOC 32-bit es inválido, prueba 16-bit en 30845 (Input)
            if bat_soc is None:
                try:
                    _, _, soc16_regs = _try_read_register_block(
                        battery_client, SMA_REG_BAT_SOC, 1, self.battery_slave
                    )
                    dec_soc16 = BinaryPayloadDecoder.fromRegisters(
                        soc16_regs.registers, byteorder=Endian.Big
                    )
                    soc16 = _norm_u16(dec_soc16.decode_16bit_uint())
                    if soc16 is not None and 0 <= soc16 <= 100:
                        bat_soc = soc16
                except Exception:
                    pass

            # Defaults de seguridad
            if bat_power is None:
                bat_power = 0
            if bat_soc is None:
                bat_soc = 0
            if bat_capacity is None:
                bat_capacity = 0

            kind_grid, addr_grid, grid_regs = _try_read_register_block(
                battery_client, SMA_REG_GRID_POWER, 2, self.battery_slave
            )

            decoder_grid = BinaryPayloadDecoder.fromRegisters(
                grid_regs.registers, byteorder=Endian.Big, wordorder=Endian.Little
            )
            ongrid_power_raw = decoder_grid.decode_32bit_int()
            ongrid_power = _norm_s32(ongrid_power_raw) or 0

            _LOGGER.debug(
                "Datos Batería OK: SOC=%s%%, BatPower=%sW, GridPower=%sW",
                bat_soc,
                bat_power,
                ongrid_power,
            )

            # --- 2. Leer Inversor FV (Obligatorio) ---
            _LOGGER.debug("Conectando a Inversor FV: %s", self.pv_ip)
            pv_client.connect()

            kind_pv, addr_pv, pv_regs = _try_read_register_block(
                pv_client, SMA_REG_PV_POWER, 2, self.pv_slave
            )

            decoder_pv = BinaryPayloadDecoder.fromRegisters(
                pv_regs.registers, byteorder=Endian.Big, wordorder=Endian.Little
            )
            pv_power_raw = decoder_pv.decode_32bit_int()
            pv_power = _norm_s32(pv_power_raw) or 0

            _LOGGER.debug("Datos FV OK: PVPower=%sW", pv_power)

            # --- 3. Construir Payload (Éxito) ---
            telemetry_data = {
                KEY_BAT_SOC: bat_soc,
                KEY_BAT_POWER: bat_power,
                KEY_PV_POWER: pv_power,
                KEY_GRID_POWER: ongrid_power,
                KEY_BAT_CHARGE_ALLOWED: bat_charge_allowed,  # placeholders
                KEY_BAT_DISCHARGE_ALLOWED: bat_discharge_allowed,
                KEY_BAT_CAPACITY: bat_capacity,
                KEY_TOTAL_GRID_OUTPUT: 0,
            }
            return telemetry_data  # Devuelve NÚMEROS

        except Exception as e:
            _LOGGER.warning("No se pudo obtener telemetría de SMA Modbus: %s", e)
            return None

        finally:
            try:
                if hasattr(battery_client, "is_socket_open") and battery_client.is_socket_open():
                    battery_client.close()
                else:
                    battery_client.close()
            except Exception:
                pass
            try:
                if hasattr(pv_client, "is_socket_open") and pv_client.is_socket_open():
                    pv_client.close()
                else:
                    pv_client.close()
            except Exception:
                pass
            _LOGGER.debug("Conexión Modbus cerrada.")

    # --- Escritura Pysma (AÑADIDA) ---
    async def _async_write_speedwire_commands(self, commands: dict[str, Any]) -> None:
        """[FUNCIÓN ASÍNCRONA] Escribe comandos en el Sunny Home Manager."""
        if not self.shm_ip or not self.shm_password:
            _LOGGER.warning(
                "Se recibieron comandos de API, pero la IP o contraseña del "
                "Sunny Home Manager (SHM) no están configurados. Omitiendo escritura."
            )
            return

        _LOGGER.debug(
            "Recibidos comandos de API para escribir en SHM (Speedwire): %s", commands
        )

        sma = pysma.SMA(
            self.hass.helpers.aiohttp_client.async_get_clientsession(),
            self.shm_ip,
            self.shm_password,
            self.shm_group,
        )

        try:
            if not await sma.new_session():
                _LOGGER.error(
                    "No se pudo iniciar sesión en el Sunny Home Manager. ¿Contraseña o IP incorrectas?"
                )
                return

            _LOGGER.debug("Sesión iniciada en Sunny Home Manager (%s)", self.shm_ip)

            # (Lógica de escritura comentada)
            _LOGGER.warning(
                "La lógica de escritura Speedwire (_async_write_speedwire_commands) "
                "ha sido llamada, pero las 'Keys' (Object IDs) están comentadas."
            )

        except Exception as e:
            _LOGGER.error("Error al escribir comandos Speedwire/pysma: %s", e)
        finally:
            _LOGGER.debug("Cerrando sesión de Sunny Home Manager.")
            await sma.close_session()

    # --- Ciclo de actualización: devuelve datos numéricos ---
    async def _async_update_data(self) -> dict[str, Any]:
        """Ciclo de actualización unificado (Versión Modbus)."""
        entry_id = self.config_entry.entry_id
        is_enabled = self.hass.data[DOMAIN].get(entry_id, {}).get("is_enabled", True)

        if not is_enabled:
            _LOGGER.debug(
                "Sondeo Modbus deshabilitado por el interruptor. Omitiendo ciclo."
            )
            if self.data is None:
                return {}
            return self.data

        _LOGGER.debug("Iniciando ciclo de actualización Modbus SMA...")

        telemetry_data_numeric: dict[str, Any] | None

        # 1. Leer datos Modbus (devuelve números)
        telemetry_data_numeric = await self.hass.async_add_executor_job(
            self._read_sma_telemetry
        )

        if telemetry_data_numeric is None:
            _LOGGER.debug("Construyendo telemetría a cero por fallo de Modbus.")
            # Datos numéricos para los sensores
            telemetry_data_numeric = {
                KEY_BAT_SOC: 0,
                KEY_BAT_POWER: 0,
                KEY_PV_POWER: 0,
                KEY_GRID_POWER: 0,
                KEY_BAT_CHARGE_ALLOWED: False,
                KEY_BAT_DISCHARGE_ALLOWED: False,
                KEY_BAT_CAPACITY: 0,
                KEY_TOTAL_GRID_OUTPUT: 0,
            }
        else:
            _LOGGER.debug("Telemetría Modbus SMA real obtenida.")

        # 2. (opcional) Formateo para API externa
        telemetry_data_for_api = {
            "plant_id": str(self.plant_id),
            "bat_soc": str(telemetry_data_numeric.get(KEY_BAT_SOC, 0)),
            "bat_power": str(telemetry_data_numeric.get(KEY_BAT_POWER, 0)),
            "pv_power": str(telemetry_data_numeric.get(KEY_PV_POWER, 0)),
            "ongrid_power": str(telemetry_data_numeric.get(KEY_GRID_POWER, 0)),
            "bat_charge_allowed": str(
                telemetry_data_numeric.get(KEY_BAT_CHARGE_ALLOWED, False)
            ).lower(),
            "bat_discharge_allowed": str(
                telemetry_data_numeric.get(KEY_BAT_DISCHARGE_ALLOWED, False)
            ).lower(),
            "bat_capacity": str(telemetry_data_numeric.get(KEY_BAT_CAPACITY, 0)),
            "total_grid_output_energy": str(
                telemetry_data_numeric.get(KEY_TOTAL_GRID_OUTPUT, 0)
            ),
        }

        # 3. Enviar telemetría (formateada) a la API de Spock
        _LOGGER.debug("Enviando telemetría a Spock API: %s", telemetry_data_for_api)
        headers = {"X-Auth-Token": self.api_token}

        try:
            async with self._session.post(
                API_ENDPOINT, headers=headers, json=telemetry_data_for_api
            ) as resp:
                if resp.status == 403:
                    raise UpdateFailed("API Token inválido (403)")
                if resp.status != 200:
                    txt = await resp.text()
                    _LOGGER.error("API error %s: %s", resp.status, txt)
                    raise UpdateFailed(f"Error de API (HTTP {resp.status})")

                command_data = await resp.json(content_type=None)

                if not isinstance(command_data, dict):
                    _LOGGER.warning(
                        "Respuesta de API inesperada (no es un dict): %s", command_data
                    )
                    raise UpdateFailed("Respuesta de API inesperada")

                _LOGGER.debug("Comandos recibidos: %s", command_data)

                # 4. Procesar comandos (Comentado)
                # if command_data.get("action") != "none" or command_data.get("status") == "ok":
                #     _LOGGER.debug("Llamando a _async_write_speedwire_commands...")
                #     await self._async_write_speedwire_commands(command_data)

                # 5. Devolver los DATOS NUMÉRICOS para los sensores
                return telemetry_data_numeric

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error("Error en el ciclo de actualización (API POST): %s", err)
            raise UpdateFailed(
                f"Error en el ciclo de actualización (API POST): {err}"
            ) from err
