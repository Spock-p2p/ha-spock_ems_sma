"""Integración Spock EMS SMA (Modbus)"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# --- Imports de Modbus (Corregidos para Pymodbus v3.x) ---
from pymodbus.client import ModbusTcpClient
from pymodbus.utilities import Endian  # <-- CAMBIO: Ruta v3.x
from pymodbus.payload import BinaryPayloadDecoder # <-- CAMBIO: Ruta v3.x
from pymodbus.payload import BinaryPayloadBuilder # <-- CAMBIO: Ruta v3.x
# --- FIN DE CAMBIOS ---

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
    DEFAULT_SCAN_INTERVAL_S,
    PLATFORMS,
    # Importar registros
    SMA_REG_BAT_POWER,
    SMA_REG_BAT_SOC,
    SMA_REG_BAT_CAPACITY,
    SMA_REG_GRID_POWER,
    SMA_REG_PV_POWER,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Configura la integración desde la entrada de configuración.
    
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
    # Descarga la entrada de configuración.
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # Recarga la entrada de configuración al modificar opciones.
    await hass.config_entries.async_reload(entry.entry_id)


class SpockEnergyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    # Coordinator que gestiona el ciclo de API unificado.

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        # Inicializa el coordinador.
        self.config_entry = entry
        self.config = {**self.config_entry.data, **self.config_entry.options}
        self.api_token: str = self.config[CONF_API_TOKEN]
        self.plant_id: int = self.config[CONF_PLANT_ID]
        
        self.battery_ip: str = self.config[CONF_BATTERY_IP]
        self.battery_port: int = self.config[CONF_BATTERY_PORT]
        self.battery_slave: int = self.config[CONF_BATTERY_SLAVE]
        
        self.pv_ip: str = self.config[CONF_PV_IP]
        self.pv_port: int = self.config[CONF_PV_PORT]
        self.pv_slave: int = self.config[CONF_PV_SLAVE]
        
        self._session = async_get_clientsession(hass)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_S),
        )

    def _read_sma_telemetry(self) -> dict[str, str] | None:
        # [FUNCIÓN SÍNCRONA] Lee los registros Modbus de los inversores SMA.
        
        _LOGGER.debug("Iniciando lectura Modbus SMA...")
        
        battery_client = ModbusTcpClient(
            host=self.battery_ip, port=self.battery_port, timeout=5
        )
        pv_client = ModbusTcpClient(
            host=self.pv_ip, port=self.pv_port, timeout=5
        )
        
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
            
            bat_regs = battery_client.read_holding_registers(
                address=SMA_REG_BAT_POWER, 
                count=7,
                slave=self.battery_slave
            )
            if bat_regs.isError():
                raise ConnectionError(f"Error al leer registros de batería: {bat_regs}")

            decoder_bat = BinaryPayloadDecoder.fromRegisters(
                bat_regs.registers, byteorder=Endian.BIG # CAMBIO: v3 usa enum
            )
            bat_power = decoder_bat.decode_32bit_int()
            bat_soc = decoder_bat.decode_32bit_uint()
            decoder_bat.skip_bytes(4)
            bat_capacity = decoder_bat.decode_32bit_uint()

            grid_regs = battery_client.read_holding_registers(
                address=SMA_REG_GRID_POWER, 
                count=2,
                slave=self.battery_slave
            )
            if grid_regs.isError():
                raise ConnectionError(f"Error al leer registros de red: {grid_regs}")
            
            decoder_grid = BinaryPayloadDecoder.fromRegisters(
                grid_regs.registers, byteorder=Endian.BIG # CAMBIO: v3 usa enum
            )
            ongrid_power = decoder_grid.decode_32bit_int()
            
            _LOGGER.debug(f"Datos Batería OK: SOC={bat_soc}%, BatPower={bat_power}W, GridPower={ongrid_power}W")

            # --- 2. Leer Inversor FV (Obligatorio) ---
            _LOGGER.debug("Conectando a Inversor FV: %s", self.pv_ip)
            pv_client.connect()
            
            pv_regs = pv_client.read_holding_registers(
                address=SMA_REG_PV_POWER, 
                count=2,
                slave=self.pv_slave
            )
            if pv_regs.isError():
                raise ConnectionError(f"Error al leer registros FV: {pv_regs}")

            decoder_pv = BinaryPayloadDecoder.fromRegisters(
                pv_regs.registers, byteorder=Endian.BIG # CAMBIO: v3 usa enum
            )
            pv_power = decoder_pv.decode_32bit_int()
            _LOGGER.debug(f"Datos FV OK: PVPower={pv_power}W")
            

            # --- 3. Construir Payload (Éxito) ---
            telemetry_data = {
                "plant_id": str(self.plant_id),
                "bat_soc": str(bat_soc),
                "bat_power": str(bat_power),
                "pv_power": str(pv_power),
                "ongrid_power": str(ongrid_power),
                "bat_charge_allowed": str(bat_charge_allowed).lower(),
                "bat_discharge_allowed": str(bat_discharge_allowed).lower(),
                "bat_capacity": str(bat_capacity),
                "total_grid_output_energy": "0" 
            }
            return telemetry_data

        except Exception as e:
            _LOGGER.warning(f"No se pudo obtener telemetría de SMA Modbus: {e}")
            return None 
        
        finally:
            if battery_client.is_socket_open():
                battery_client.close()
            if pv_client.is_socket_open():
                pv_client.close()
            _LOGGER.debug("Conexión Modbus cerrada.")


    def _write_modbus_commands(self, commands: dict[str, Any]) -> None:
        # [FUNCIÓN SÍNCRONA] Escribe los comandos de la API en el inversor.
        # ADVERTENCIA: SMA NO USA MODBUS PARA ESCRITURA DE BATERÍA.
        _LOGGER.warning(
            "Se ha llamado a la función de escritura Modbus para SMA, "
            "pero SMA no soporta control de batería vía Modbus TCP. "
            "Esta función es solo una plantilla y no tendrá efecto."
        )
        pass


    async def _async_update_data(self) -> dict[str, Any]:
        # Ciclo de actualización unificado (Versión Modbus)
        
        entry_id = self.config_entry.entry_id
        is_enabled = self.hass.data[DOMAIN].get(entry_id, {}).get("is_enabled", True)
        
        if not is_enabled:
            _LOGGER.debug("Sondeo Modbus deshabilitado por el interruptor. Omitiendo ciclo.")
            if self.data is None: 
                 return {} 
            return self.data 

        _LOGGER.debug("Iniciando ciclo de actualización Modbus SMA...")
        
        telemetry_data: dict[str, str] = {}
        
        telemetry_data_or_none = await self.hass.async_add_executor_job(
            self._read_sma_telemetry
        )

        if telemetry_data_or_none is None:
            _LOGGER.debug("Construyendo telemetría a cero por fallo de Modbus.")
            telemetry_data = {
                "plant_id": str(self.plant_id),
                "bat_soc": "0", "bat_power": "0", "pv_power": "0",
                "ongrid_power": "0", "bat_charge_allowed": "false",
                "bat_discharge_allowed": "false", "bat_capacity": "0",
                "total_grid_output_energy": "0"
            }
        else:
            _LOGGER.debug("Telemetría Modbus SMA real obtenida.")
            telemetry_data = telemetry_data_or_none
        
        _LOGGER.debug("Enviando telemetría a Spock API: %s", telemetry_data)
        headers = {"X-Auth-Token": self.api_token}
        
        try:
            async with self._session.post(
                API_ENDPOINT, 
                headers=headers, 
                json=telemetry_data 
            ) as resp:
                
                if resp.status == 403:
                    raise UpdateFailed("API Token inválido (403)")
                if resp.status != 200:
                    txt = await resp.text()
                    _LOGGER.error("API error %s: %s", resp.status, txt)
                    raise UpdateFailed(f"Error de API (HTTP {resp.status})")

                command_data = await resp.json(content_type=None)
                
                if not isinstance(command_data, dict):
                    _LOGGER.warning("Respuesta de API inesperada (no es un dict): %s", command_data)
                    raise UpdateFailed("Respuesta de API inesperada")

                _LOGGER.debug("Comandos recibidos: %s", command_data)
                
                # (Lógica de escritura comentada)
                
                return command_data

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error("Error en el ciclo de actualización (API POST): %s", err)
            raise UpdateFailed(f"Error en el ciclo de actualización (API POST): {err}") from err
