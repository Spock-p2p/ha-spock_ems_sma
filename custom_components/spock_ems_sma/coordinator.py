import logging
import async_timeout
import json
from aiohttp import ClientSession, ClientError
from typing import Optional, Dict, Any

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from pysma import (
    SMAWebConnect,
    SmaAuthenticationException,
    SmaConnectionException,
    SmaReadException,
)
from pysma.helpers import DeviceInfo 

from .const import DOMAIN, SCAN_INTERVAL_SMA

_LOGGER = logging.getLogger(__name__)

def to_int_str_or_none(val: Any) -> Optional[str]:
    """Convierte un valor a int-string, o devuelve None (objeto)."""
    if val is None:
        return None
    try:
        # Convertimos a float, luego a int (para truncar), luego a str
        return str(int(float(val)))
    except (ValueError, TypeError):
        return None # Devuelve None (objeto)

class SmaTelemetryCoordinator(DataUpdateCoordinator):
    """
    Coordina la obtención de datos de SMA (PULL) y
    el envío de telemetría a Spock (PUSH).
    """

    def __init__(
        self, 
        hass, 
        pysma_api: SMAWebConnect, 
        http_session: ClientSession,
        api_token: str,
        plant_id: str,
        spock_api_url: str
    ):
        """Inicializa el coordinador."""
        self.pysma_api = pysma_api
        self.hass = hass
        self._http_session = http_session
        self._spock_api_url = spock_api_url
        self._plant_id = plant_id
        
        self._headers = {
            "X-Auth-Token": api_token, 
            "Content-Type": "application/json",
        }
        
        self.sensors = None
        self.polling_enabled = True 
        
        self.sma_device_info: Optional[DeviceInfo] = None
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} Telemetry",
            update_interval=SCAN_INTERVAL_SMA,
        )

    async def async_initialize_sensors(self):
        """Obtiene la info del dispositivo y la lista de sensores."""
        try:
            _LOGGER.info("Obteniendo información del dispositivo SMA...")
            self.sma_device_info = await self.pysma_api.device_info()
            _LOGGER.info(f"Dispositivo encontrado: {self.sma_device_info.name} (Serial: {self.sma_device_info.serial})")

            _LOGGER.info("Obteniendo lista de sensores de SMA...")
            self.sensors = await self.pysma_api.get_sensors()
            _LOGGER.info(f"Encontrados {len(self.sensors)} sensores en SMA.")
            
        except Exception as e:
            _LOGGER.error(f"Error al inicializar sensores de pysma: {e}")
            raise UpdateFailed(f"No se pudo obtener la lista de sensores: {e}")

    async def _async_update_data(self) -> Dict[str, Any]:
        """
        Función principal de polling.
        Paso 1: PULL de datos de SMA (usando pysma).
        Paso 2: PUSH de datos a Spock.
        """
        
        if not self.polling_enabled:
            _LOGGER.debug("Operativa global desactivada por el switch maestro. Saltando PULL/PUSH.")
            return self.data 

        if not self.sensors:
            raise UpdateFailed("La lista de sensores de SMA no está inicializada.")
        
        sensors_dict = {}
        try:
            await self.pysma_api.read(self.sensors)
            sensors_dict = {s.name: s.value for s in self.sensors}
            _LOGGER.debug(f"Datos PULL de SMA recibidos: {sensors_dict}")

        except (SmaReadException, SmaConnectionException) as err:
            raise UpdateFailed(f"Error al leer SMA: {err}")
        except SmaAuthenticationException as err:
            _LOGGER.warning(f"Autenticación de SMA fallida, se re-intentará: {err}")
            raise UpdateFailed(f"Autenticación de SMA fallida: {err}")
        
        try:
            spock_payload = self._map_sma_to_spock(sensors_dict)
            await self._async_push_to_spock(spock_payload)
        except Exception as e:
            _LOGGER.error(f"Error al hacer PUSH de telemetría a Spock: {e}")

        return sensors_dict

    def _map_sma_to_spock(self, sensors_dict: dict) -> dict:
        """
        Toma el diccionario de sensores de pysma y lo mapea
        al payload que espera la API de Spock.
        """
        
        # 1. Potencia de Batería
        charge = sensors_dict.get("battery_power_charge_total", 0) or 0
        discharge = sensors_dict.get("battery_power_discharge_total", 0) or 0
        battery_power = charge - discharge

        # 2. PV Power (Suma de strings A y B)
        pv_a = sensors_dict.get("pv_power_a", 0) or 0
        pv_b = sensors_dict.get("pv_power_b", 0) or 0
        pv_power = pv_a + pv_b
        
        # --- ¡CORRECCIÓN DE LÓGICA DE RED (SEGÚN TU PETICIÓN)! ---
        # Usamos los sensores del 'metering' (contador)
        grid_absorb = sensors_dict.get("metering_power_absorbed", 0) or 0
        grid_supply = sensors_dict.get("metering_power_supplied", 0) or 0
        
        # 'ongrid_power' = valor neto (Importación - Exportación)
        net_grid_power = grid_absorb - grid_supply
        
        # 'total_grid_output_energy' = valor de exportación bruta
        # (Tal como pediste, usamos 'metering_power_supplied' para esto)
        supply_power = grid_supply
        # --- FIN DE LA CORRECCIÓN ---

        # 4. Mapeo final
        spock_payload = {
            "plant_id": str(self._plant_id),
            "bat_soc": to_int_str_or_none(sensors_dict.get("battery_soc_total")),
            "bat_power": to_int_str_or_none(battery_power),
            "pv_power": to_int_str_or_none(pv_power),
            "ongrid_power": to_int_str_or_none(net_grid_power), # <-- Valor NETO
            "bat_charge_allowed": "true",
            "bat_discharge_allowed": "true",
            "bat_capacity": "0",
            "total_grid_output_energy": to_int_str_or_none(supply_power) # <-- Valor BRUTO EXPORT
        }
        
        return spock_payload


    async def _async_push_to_spock(self, spock_payload: dict):
        """Envía la telemetría formateada a la API de Spock."""
        
        _LOGGER.debug(f"Haciendo PUSH a {self._spock_api_url} con payload: {spock_payload}")
        
        serialized_payload = json.dumps(spock_payload)
        
        try:
            async with async_timeout.timeout(10):
                response = await self._http_session.post(
                    self._spock_api_url,
                    data=serialized_payload,
                    headers=self._headers,
                )
                response.raise_for_status()
                _LOGGER.debug(f"PUSH a Spock exitoso (Status: {response.status})")

        except ClientError as e:
            _LOGGER.warning(f"Error de red en PUSH a Spock: {e}")
        except Exception as e:
            _LOGGER.error(f"Error inesperado en PUSH a Spock: {e}")
            raise
