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

# --- Imports de Modbus ---
from pymodbus.client import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.payload import BinaryPayloadBuilder

# --- CAMBIO: Imports de Speedwire (pysma) ---
import pysma
# --- FIN CAMBIO ---

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
    # --- CAMBIO ---
    CONF_SHM_IP,
    CONF_SHM_GROUP,
    CONF_SHM_PASSWORD,
    # --- FIN CAMBIO ---
    DEFAULT_SCAN_INTERVAL_S,
    PLATFORMS,
    SMA_REG_BAT_POWER,
    SMA_REG_BAT_SOC,
    SMA_REG_BAT_CAPACITY,
    SMA_REG_GRID_POWER,
    SMA_REG_PV_POWER,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura la integración desde la entrada de configuración."""
    
    coordinator = SpockEnergyCoordinator(hass, entry) 

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "is_enabled": True, 
    }

    await asyncio.sleep(2)
    await coordinator.async_config_entry_first_refresh()
    _LOGGER.info("Spock EMS SMA: Primer fetch realizado.")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
         "Spock EMS SMA: Ciclo automático (gestionado por listener) iniciado cada %s.", 
         coordinator.update_interval
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
        """Inicializa el coordinador."""
        self.config_entry = entry
        self.config = {**entry.data, **entry.options}
        self.api_token: str = self.config[CONF_API_TOKEN]
        self.plant_id: int = self.config[CONF_PLANT_ID]
        
        # Configuración Modbus (Lectura)
        self.battery_ip: str = self.config[CONF_BATTERY_IP]
        self.battery_port: int = self.config[CONF_BATTERY_PORT]
        self.battery_slave: int = self.config[CONF_BATTERY_SLAVE]
        self.pv_ip: str = self.config[CONF_PV_IP]
        self.pv_port: int = self.config[CONF_PV_PORT]
        self.pv_slave: int = self.config[CONF_PV_SLAVE]
        
        self.battery_client = ModbusTcpClient(
            host=self.battery_ip, port=self.battery_port, timeout=5
        )
        self.pv_client = ModbusTcpClient(
            host=self.pv_ip, port=self.pv_port, timeout=5
        )
        
        # --- CAMBIO: Configuración Speedwire (Escritura) ---
        self.shm_ip: str | None = self.config.get(CONF_SHM_IP)
        self.shm_group: str | None = self.config.get(CONF_SHM_GROUP)
        self.shm_password: str | None = self.config.get(CONF_SHM_PASSWORD)
        self.sma_session = None
        # --- FIN CAMBIO ---
        
        self._session = async_get_clientsession(hass)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_S),
        )

    def _read_sma_telemetry(self) -> dict[str, str]:
        """
        [FUNCIÓN SÍNCRONA] Lee los registros Modbus de los inversores SMA.
        """
        # ... (Esta función es la misma que en el mensaje anterior, no la repito por brevedad) ...
        # ... (Lee de self.battery_client y self.pv_client) ...
        
        _LOGGER.debug("Iniciando lectura Modbus SMA...")
        
        # Valores por defecto
        bat_soc = 0
        bat_power = 0
        pv_power = 0
        ongrid_power = 0
        bat_capacity = 0
        bat_charge_allowed = True
        bat_discharge_allowed = True

        # --- 1. Leer Inversor de Batería (Obligatorio) ---
        try:
            _LOGGER.debug("Conectando a Inversor Batería: %s", self.battery_ip)
            self.battery_client.connect()
            
            bat_regs = self.battery_client.read_holding_registers(
                address=SMA_REG_BAT_POWER, 
                count=7, # 30843 a 30849
                slave=self.battery_slave
            )
            if bat_regs.isError():
                raise ConnectionError(f"Error al leer registros de batería: {bat_regs}")

            decoder_bat = BinaryPayloadDecoder.fromRegisters(
                bat_regs.registers, byteorder=Endian.Big
            )
            bat_power = decoder_bat.decode_32bit_int()    # 30843
            bat_soc = decoder_bat.decode_32bit_uint()       # 30845
            decoder_bat.skip_bytes(4)                       # 30847
            bat_capacity = decoder_bat.decode_32bit_uint()  # 30849

            grid_regs = self.battery_client.read_holding_registers(
                address=SMA_REG_GRID_POWER, 
                count=2, # 30867
                slave=self.battery_slave
            )
            if grid_regs.isError():
                raise ConnectionError(f"Error al leer registros de red: {grid_regs}")
            
            decoder_grid = BinaryPayloadDecoder.fromRegisters(
                grid_regs.registers, byteorder=Endian.Big
            )
            ongrid_power = decoder_grid.decode_32bit_int()
            
            _LOGGER.debug(f"Datos Batería OK: SOC={bat_soc}%, BatPower={bat_power}W, GridPower={ongrid_power}W")

        except Exception as e:
            _LOGGER.warning(f"Error al leer datos del inversor de batería SMA: {e}")
            raise 
        finally:
            if self.battery_client.is_socket_open():
                self.battery_client.close()

        # --- 2. Leer Inversor FV (Obligatorio) ---
        try:
            _LOGGER.debug("Conectando a Inversor FV: %s", self.pv_ip)
            self.pv_client.connect()
            
            pv_regs = self.pv_client.read_holding_registers(
                address=SMA_REG_PV_POWER, 
                count=2, # 30775
                slave=self.pv_slave
            )
            if pv_regs.isError():
                raise ConnectionError(f"Error al leer registros FV: {pv_regs}")

            decoder_pv = BinaryPayloadDecoder.fromRegisters(
                pv_regs.registers, byteorder=Endian.Big
            )
            pv_power = decoder_pv.decode_32bit_int()
            _LOGGER.debug(f"Datos FV OK: PVPower={pv_power}W")
            
        except Exception as e:
            _LOGGER.warning(f"No se pudo leer el inversor FV en {self.pv_ip}: {e}")
            raise
        finally:
            if self.pv_client.is_socket_open():
                self.pv_client.close()

        # --- 3. Construir Payload ---
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


    # --- CAMBIO: Nueva función de escritura (asíncrona) ---
    async def _async_write_speedwire_commands(self, commands: dict[str, Any]) -> None:
        """
        [FUNCIÓN ASÍNCRONA] Escribe comandos en el Sunny Home Manager
        usando el protocolo Speedwire (pysma).
        
        !!! ESTA ES LA FUNCIÓN QUE DEBES ADAPTAR !!!
        """
        
        # 1. Comprobar si la escritura está configurada
        if not self.shm_ip or not self.shm_password:
            _LOGGER.warning(
                "Se recibieron comandos de API, pero la IP o contraseña del "
                "Sunny Home Manager (SHM) no están configurados. Omitiendo escritura."
            )
            return

        _LOGGER.debug("Recibidos comandos de API para escribir en SHM (Speedwire): %s", commands)
        
        # 2. Inicializar cliente pysma (usa la sesión aiohttp de HA)
        sma = pysma.SMA(
            self.hass.helpers.aiohttp_client.async_get_clientsession(), 
            self.shm_ip, 
            self.shm_password, 
            self.shm_group
        )
        
        try:
            # 3. Iniciar sesión
            if not await sma.new_session():
                _LOGGER.error("No se pudo iniciar sesión en el Sunny Home Manager. ¿Contraseña o IP incorrectas?")
                return

            _LOGGER.debug("Sesión iniciada en Sunny Home Manager (%s)", self.shm_ip)

            # --- INICIO DE LÓGICA DE ESCRITURA (EJEMPLO) ---
            
            # NOTA: Debes encontrar los "Key" (son Object IDs) correctos 
            # para tu modelo de Home Manager.
            # Estos son ejemplos comunes, pero pueden no funcionar.
            
            # Key para forzar la carga de la batería (en W)
            # KEY_FORZAR_CARGA = "6315_402366F4" # (Ejemplo: Carga activa desde red)
            
            # Key para forzar la descarga de la batería (en W)
            # KEY_FORZAR_DESCARGA = "6316_402366F4" # (Ejemplo: Descarga activa)

            operation = commands.get("battery_operation")
            action = commands.get("action")
            amount = int(commands.get("amount", 0))

            if operation == "manual" and action == "charge":
                _LOGGER.info(f"Enviando comando Speedwire: Forzar Carga de {amount}W")
                # await sma.set_values({
                #     KEY_FORZAR_DESCARGA: 0, # Poner el opuesto a 0
                #     KEY_FORZAR_CARGA: amount
                # })
                
            elif operation == "manual" and action == "discharge":
                _LOGGER.info(f"Enviando comando Speedwire: Forzar Descarga de {amount}W")
                # await sma.set_values({
                #     KEY_FORZAR_CARGA: 0,
                #     KEY_FORZAR_DESCARGA: amount
                # })

            elif operation == "auto":
                _LOGGER.info("Enviando comando Speedwire: Modo Automático")
                # await sma.set_values({
                #     KEY_FORZAR_CARGA: 0,
                #     KEY_FORZAR_DESCARGA: 0
                # })
            
            _LOGGER.warning(
                "La lógica de escritura Speedwire (_async_write_speedwire_commands) "
                "ha sido llamada, pero las 'Keys' (Object IDs) están comentadas. "
                "Debes editar __init__.py para habilitarlas."
            )
            
            # --- FIN DE LÓGICA DE ESCRITURA ---

        except Exception as e:
            _LOGGER.error(f"Error al escribir comandos Speedwire/pysma: {e}")
        finally:
            _LOGGER.debug("Cerrando sesión de Sunny Home Manager.")
            await sma.close_session()
    # --- FIN DEL CAMBIO ---


    async def _async_update_data(self) -> dict[str, Any]:
        """
        Ciclo de actualización unificado (Versión Modbus)
        """
        
        entry_id = self.config_entry.entry_id
        is_enabled = self.hass.data[DOMAIN].get(entry_id, {}).get("is_enabled", True)
        
        if not is_enabled:
            _LOGGER.debug("Sondeo Modbus deshabilitado por el interruptor. Omitiendo ciclo.")
            return self.data 

        _LOGGER.debug("Iniciando ciclo de actualización Modbus SMA...")
        
        telemetry_data: dict[str, str] = {}
        
        try:
            telemetry_data = await self.hass.async_add_executor_job(
                self._read_sma_telemetry
            )
            _LOGGER.debug("Telemetría Modbus SMA real obtenida.")

        except Exception as e:
            _LOGGER.warning(f"No se pudo obtener telemetría de SMA Modbus: {e}. Enviando telemetría a cero.")
            telemetry_data = {
                "plant_id": str(self.plant_id),
                "bat_soc": "0", "bat_power": "0", "pv_power": "0",
                "ongrid_power": "0", "bat_charge_allowed": "false",
                "bat_discharge_allowed": "false", "bat_capacity": "0",
                "total_grid_output_energy": "0"
            }
        
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
                
                # --- CAMBIO: Lógica de escritura (comentada) ---
                # 4. Procesar comandos (si hay algo que hacer)
                # if command_data.get("action") != "none" or command_data.get("status") == "ok":
                #    _LOGGER.debug("Llamando a _async_write_speedwire_commands...")
                #    await self._async_write_speedwire_commands(command_data)
                # --- FIN DEL CAMBIO ---
                
                return command_data

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error("Error en el ciclo de actualización (API POST): %s", err)
            raise UpdateFailed(f"Error en el ciclo de actualización (API POST): {err}") from err
