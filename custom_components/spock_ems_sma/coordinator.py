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
from .const import DOMAIN, SCAN_INTERVAL_SMA

_LOGGER = logging.getLogger(__name__)

class SmaTelemetryCoordinator(DataUpdateCoordinator):
    """Coordina la obtención de datos (SMA) y el envío (Spock)."""

    def __init__(
        self, 
        hass, 
        pysma_api: SMAWebConnect, 
        http_session: ClientSession,
        api_token: str,
        plant_id: str,
        spock_api_url: str
    ):
        self.pysma_api = pysma_api
        self.hass = hass
        self._http_session = http_session
        self._spock_api_url = spock_api_url
        self._plant_id = plant_id
        
        # Headers fijos para la API de Spock
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        
        self.sensors = None
        self.polling_enabled = True # Controlado por switch.py
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} Telemetry",
            update_interval=SCAN_INTERVAL_SMA,
        )

    async def async_initialize_sensors(self):
        try:
            _LOGGER.info("Obteniendo lista de sensores de SMA...")
            self.sensors = await self.pysma_api.get_sensors()
            _LOGGER.info(f"Encontrados {len(self.sensors)} sensores en SMA.")
        except Exception as e:
            raise UpdateFailed(f"No se pudo obtener la lista de sensores: {e}")

    async def _async_update_data(self) -> Dict[str, Any]:
        # 1. Verificar interruptor maestro
        if not self.polling_enabled:
            _LOGGER.debug("Operativa pausada por interruptor maestro.")
            return self.data

        if not self.sensors:
            raise UpdateFailed("Sensores SMA no inicializados.")
        
        # 2. PULL de SMA
        sensors_dict = {}
        try:
            await self.pysma_api.read(self.sensors)
            sensors_dict = {s.name: s.value for s in self.sensors}
            _LOGGER.debug(f"Datos PULL SMA: {sensors_dict}")
        except (SmaReadException, SmaConnectionException) as err:
            raise UpdateFailed(f"Error lectura SMA: {err}")
        except SmaAuthenticationException as err:
            _LOGGER.warning(f"Error auth SMA, se reintentará: {err}")
            raise UpdateFailed(f"Error auth SMA: {err}")
        
        # 3. PUSH a Spock
        try:
            payload = self._map_sma_to_spock(sensors_dict)
            await self._async_push_to_spock(payload)
        except Exception as e:
            _LOGGER.error(f"Error en PUSH a Spock: {e}")

        return sensors_dict

    def _map_sma_to_spock(self, s: dict) -> dict:
        """Mapea datos de SMA al formato de Spock."""
        # Cálculos auxiliares
        charge = s.get("battery_power_charge_total", 0) or 0
        discharge = s.get("battery_power_discharge_total", 0) or 0
        bat_power = charge - discharge
        pv_power = (s.get("pv_power_a", 0) or 0) + (s.get("pv_power_b", 0) or 0)
        grid_power = s.get("grid_power")

        return {
            "plant_id": str(self._plant_id),
            "bat_soc": str(s.get("battery_soc_total")),
            "bat_power": str(bat_power),
            "pv_power": str(pv_power),
            "ongrid_power": str(grid_power),
            "bat_charge_allowed": "true",
            "bat_discharge_allowed": "true",
            "bat_capacity": "0",
            "total_grid_output_energy": str(grid_power)
        }

    async def _async_push_to_spock(self, payload: dict):
        """Envía datos a Spock usando serialización manual."""
        _LOGGER.debug(f"PUSH a {self._spock_api_url}: {payload}")
        
        # Serialización manual para máxima compatibilidad
        data_str = json.dumps(payload)
        
        try:
            async with async_timeout.timeout(10):
                response = await self._http_session.post(
                    self._spock_api_url,
                    data=data_str,      # Usamos 'data' con string JSON
                    headers=self._headers # Headers incluyen Content-Type
                )
                response.raise_for_status()
                _LOGGER.debug(f"PUSH exitoso: {response.status}")
        except ClientError as e:
            _LOGGER.warning(f"Error red PUSH Spock: {e}")
        except Exception as e:
            _LOGGER.error(f"Error inesperado PUSH Spock: {e}")
            raise
