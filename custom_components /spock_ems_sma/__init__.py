"""Integración Spock EMS Modbus (Plantilla)"""
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

from .const import (
    DOMAIN,
    API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_PLANT_ID,
    CONF_MODBUS_IP,
    CONF_MODBUS_PORT,
    CONF_MODBUS_SLAVE,
    DEFAULT_SCAN_INTERVAL_S,
    PLATFORMS,
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
    _LOGGER.info("Spock EMS Modbus: Primer fetch realizado.")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
         "Spock EMS Modbus: Ciclo automático (gestionado por listener) iniciado cada %s.", 
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
        
        # Configuración Modbus
        self.modbus_ip: str = self.config[CONF_MODBUS_IP]
        self.modbus_port: int = self.config[CONF_MODBUS_PORT]
        self.modbus_slave: int = self.config[CONF_MODBUS_SLAVE]
        
        # Cliente Modbus (se crea aquí pero se usa en un hilo)
        self.modbus_client = ModbusTcpClient(
            host=self.modbus_ip, 
            port=self.modbus_port,
            timeout=5 # Timeout de 5 segundos
        )
        
        self._session = async_get_clientsession(hass)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_S),
        )

    def _read_modbus_data(self) -> dict[str, str]:
        """
        [FUNCIÓN SÍNCRONA] Lee los registros Modbus del inversor.
        Esta función se ejecutará en un hilo de Home Assistant.
        
        !!! ESTA ES LA FUNCIÓN QUE DEBES ADAPTAR PARA CADA MARCA !!!
        """
        _LOGGER.debug("Intentando conectar a Modbus en %s:%s", self.modbus_ip, self.modbus_port)
        
        try:
            self.modbus_client.connect()
            
            # --- INICIO DE LÓGICA DE LECTURA (EJEMPLO) ---
            # (Estos registros son ficticios. Debes reemplazarlos
            # por los registros reales de Growatt, SMA, etc.)

            # Ejemplo: Leer 10 registros (holding registers) desde la dirección 1000
            # (count=10 significa 10 registros de 16 bits)
            read_result = self.modbus_client.read_holding_registers(
                address=1000, 
                count=10, 
                slave=self.modbus_slave
            )
            
            if read_result.isError():
                raise ConnectionError(f"Error al leer registros Modbus: {read_result}")

            # Decodificar los 10 registros (20 bytes)
            decoder = BinaryPayloadDecoder.fromRegisters(
                read_result.registers, 
                byteorder=Endian.Big, # O Endian.Little, depende del inversor
                wordorder=Endian.Little
            )
            
            # Ejemplo de decodificación (depende 100% del inversor)
            bat_soc = decoder.decode_16bit_uint()       # 2 bytes
            bat_power = decoder.decode_32bit_int()      # 4 bytes
            pv_power = decoder.decode_32bit_int()       # 4 bytes
            ongrid_power = decoder.decode_32bit_int()   # 4 bytes
            bat_capacity = decoder.decode_16bit_uint()  # 2 bytes
            
            # Para los booleanos (esto es un ejemplo, podría ser un registro de bits)
            # Leer un registro de estado (ej. 1010)
            status_result = self.modbus_client.read_holding_registers(1010, 1, self.modbus_slave)
            status_word = status_result.registers[0]
            
            # Asumir bit 0 para carga, bit 1 para descarga
            bat_charge_allowed = (status_word & 0b00000001) > 0 
            bat_discharge_allowed = (status_word & 0b00000010) > 0
            
            # --- FIN DE LÓGICA DE LECTURA ---

            # Construir el payload para la API de Spock
            telemetry_data = {
                "plant_id": str(self.plant_id),
                "bat_soc": str(bat_soc),
                "bat_power": str(bat_power),
                "pv_power": str(pv_power),
                "ongrid_power": str(ongrid_power),
                "bat_charge_allowed": str(bat_charge_allowed).lower(),
                "bat_discharge_allowed": str(bat_discharge_allowed).lower(),
                "bat_capacity": str(bat_capacity),
                "total_grid_output_energy": "0" # (No lo leímos en este ejemplo)
            }
            return telemetry_data

        except Exception as e:
            _LOGGER.warning(f"Error al leer datos Modbus: {e}")
            raise # Lanzar la excepción para que _async_update_data la capture
        
        finally:
            # Asegurarse de cerrar la conexión
            if self.modbus_client.is_socket_open():
                self.modbus_client.close()
            _LOGGER.debug("Conexión Modbus cerrada.")

    def _write_modbus_commands(self, commands: dict[str, Any]) -> None:
        """
        [FUNCIÓN SÍNCRONA] Escribe los comandos de la API en el inversor.
        
        !!! ESTA ES LA FUNCIÓN QUE DEBES ADAPTAR PARA CADA MARCA !!!
        """
        _LOGGER.debug("Recibidos comandos de la API para escribir en Modbus: %s", commands)
        
        try:
            self.modbus_client.connect()

            # --- INICIO DE LÓGICA DE ESCRITURA (EJEMPLO) ---
            operation = commands.get("battery_operation")
            action = commands.get("action")
            amount = commands.get("amount", 0)

            # Ejemplo: Escribir en un registro para forzar carga/descarga
            # (¡REGISTROS Y VALORES FICTICIOS!)
            
            if operation == "manual" and action == "charge":
                _LOGGER.info("Enviando comando Modbus: Forzar Carga")
                # Ejemplo: Escribir el valor 1 en el registro 2000
                self.modbus_client.write_register(
                    address=2000, 
                    value=1, 
                    slave=self.modbus_slave
                )
                
            elif operation == "manual" and action == "discharge":
                _LOGGER.info("Enviando comando Modbus: Forzar Descarga")
                # Ejemplo: Escribir el valor 2 en el registro 2000
                self.modbus_client.write_register(
                    address=2000, 
                    value=2, 
                    slave=self.modbus_slave
                )
                
            elif operation == "auto":
                _LOGGER.info("Enviando comando Modbus: Modo Automático")
                # Ejemplo: Escribir el valor 0 en el registro 2000
                self.modbus_client.write_register(
                    address=2000, 
                    value=0, 
                    slave=self.modbus_slave
                )
            
            # Ejemplo: Escribir un límite de potencia (si la API lo envía)
            # (Esto requiere un 'BinaryPayloadBuilder')
            # builder = BinaryPayloadBuilder(byteorder=Endian.Big)
            # builder.add_16bit_int(int(amount))
            # self.modbus_client.write_registers(
            #     address=2001, 
            #     payload=builder.to_registers(), 
            #     slave=self.modbus_slave
            # )
            
            # --- FIN DE LÓGICA DE ESCRITURA ---

        except Exception as e:
            _LOGGER.error(f"Error al escribir comandos Modbus: {e}")
            raise
        finally:
            if self.modbus_client.is_socket_open():
                self.modbus_client.close()
            _LOGGER.debug("Conexión Modbus cerrada.")


    async def _async_update_data(self) -> dict[str, Any]:
        """
        Ciclo de actualización unificado (Versión Modbus)
        """
        
        entry_id = self.config_entry.entry_id
        is_enabled = self.hass.data[DOMAIN].get(entry_id, {}).get("is_enabled", True)
        
        if not is_enabled:
            _LOGGER.debug("Sondeo Modbus deshabilitado por el interruptor. Omitiendo ciclo.")
            return self.data 

        _LOGGER.debug("Iniciando ciclo de actualización Modbus...")
        
        telemetry_data: dict[str, str] = {}
        
        try:
            # 1. Ejecutar la lectura Modbus (síncrona) en un hilo
            telemetry_data = await self.hass.async_add_executor_job(
                self._read_modbus_data
            )
            _LOGGER.debug("Telemetría Modbus real obtenida.")

        except Exception as e:
            # 2. Si Modbus falla, enviar ceros (heartbeat)
            _LOGGER.warning(f"No se pudo obtener telemetría de Modbus: {e}. Enviando telemetría a cero.")
            telemetry_data = {
                "plant_id": str(self.plant_id),
                "bat_soc": "0", "bat_power": "0", "pv_power": "0",
                "ongrid_power": "0", "bat_charge_allowed": "false",
                "bat_discharge_allowed": "false", "bat_capacity": "0",
                "total_grid_output_energy": "0"
            }
        
        # 3. Enviar telemetría (real o cero) a la API de Spock
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

                # Recibimos los comandos de la API
                command_data = await resp.json(content_type=None)
                
                if not isinstance(command_data, dict):
                    _LOGGER.warning("Respuesta de API inesperada (no es un dict): %s", command_data)
                    raise UpdateFailed("Respuesta de API inesperada")

                _LOGGER.debug("Comandos recibidos: %s", command_data)
                
                # 4. Procesar comandos (si hay algo que hacer)
                # (Comprobamos 'status' por si la API devuelve "ok")
                if command_data.get("action") != "none" or command_data.get("status") == "ok":
                    await self.hass.async_add_executor_job(
                        self._write_modbus_commands, command_data
                    )
                
                # Devolvemos los comandos para que el 'switch' (listener)
                # sepa que la actualización fue exitosa
                return command_data

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error("Error en el ciclo de actualización (API POST): %s", err)
            raise UpdateFailed(f"Error en el ciclo de actualización (API POST): {err}") from err
