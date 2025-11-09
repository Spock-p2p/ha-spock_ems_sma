import logging
import async_timeout
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

from .const import DOMAIN, SCAN_INTERVAL_SMA

_LOGGER = logging.getLogger(__name__)

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
        self._http_session = http_session # Sesión para el PUSH
        self._spock_api_url = spock_api_url
        self._plant_id = plant_id
        self._headers = {"Authorization": f"Bearer {api_token}"}
        
        self.sensors = None # Lista de sensores de pysma
        
        # --- NUEVO ATRIBUTO PARA EL SWITCH ---
        self.polling_enabled = True 
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} Telemetry",
            update_interval=SCAN_INTERVAL_SMA,
        )

    async def async_initialize_sensors(self):
        """Obtiene la lista de sensores disponibles de pysma una vez."""
        try:
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
        
        # --- PASO 1: PULL (Obtener datos de SMA) ---
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
        
        # --- PASO 2: PUSH (Enviar datos a Spock Cloud) ---
        try:
            spock_payload = self._map_sma_to_spock(sensors_dict)
            await self._async_push_to_spock(spock_payload)
        except Exception as e:
            _LOGGER.error(f"Error al hacer PUSH de telemetría a Spock: {e}")

        # Devolvemos el diccionario de sensores para 'sensor.py'
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
        
        # 3. Datos de Red (grid_power)
        grid_power = sensors_dict.get("grid_power")

        # 4. Mapeo final
        spock_payload = {
            "plant_id": str(self._plant_id),
            "bat_soc": str(sensors_dict.get("battery_soc_total")),
            "bat_power": str(battery_power),
            "pv_power": str(pv_power),
            "ongrid_power": str(grid_power),
            "bat_charge_allowed": "true", # Hardcoded
            "bat_discharge_allowed": "true", # Hardcoded
            "bat_capacity": "0", # Hardcoded
            "total_grid_output_energy": str(grid_power) # Mapeado
        }
        
        # --- ¡FILTRO ELIMINADO! ---
        # Ahora el payload se enviará completo, incluyendo "None" como string,
        # exactamente igual que hacía el componente de Marstek.
        return spock_payload


    async def _async_push_to_spock(self, spock_payload: dict):
        """Envía la telemetría formateada a la API de Spock."""
        
        _LOGGER.debug(f"Haciendo PUSH a {self._spock_api_url} con payload: {spock_payload}")
        
        try:
            async with async_timeout.timeout(10):
                response = await self._http_session.post(
                    self._spock_api_url,
                    json=spock_payload,
                    headers=self._headers,
                )
                response.raise_for_status()
                _LOGGER.debug(f"PUSH a Spock exitoso (Status: {response.status})")

        except ClientError as e:
            _LOGGER.warning(f"Error de red en PUSH a Spock: {e}")
        except Exception as e:
            _LOGGER.error(f"Error inesperado en PUSH a Spock: {e}")
            raise
