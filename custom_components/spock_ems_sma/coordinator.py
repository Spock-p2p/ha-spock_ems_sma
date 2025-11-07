import logging
import async_timeout
from aiohttp import ClientSession, ClientError
from typing import Optional, Dict

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, SCAN_INTERVAL_SMA
from .sma_api import SmaApiClient, SmaApiError

_LOGGER = logging.getLogger(__name__)

class SmaTelemetryCoordinator(DataUpdateCoordinator):
    """
    Coordina la obtención de datos de SMA (PULL) y
    el envío de telemetría a Spock (PUSH).
    """

    def __init__(
        self, 
        hass, 
        api_client: SmaApiClient, 
        session: ClientSession,
        api_token: str,
        plant_id: str,
        spock_api_url: str
    ):
        """Inicializa el coordinador."""
        self.api_client = api_client
        self.hass = hass
        self._session = session
        self._spock_api_url = spock_api_url
        self._plant_id = plant_id
        self._headers = {"Authorization": f"Bearer {api_token}"}
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} Telemetry",
            update_interval=SCAN_INTERVAL_SMA,
        )

    async def _async_update_data(self):
        """
        Función principal de polling.
        Paso 1: PULL de datos de SMA.
        Paso 2: PUSH de datos a Spock.
        """
        
        # --- PASO 1: PULL (Obtener datos de SMA) ---
        try:
            sma_data_raw = await self.api_client.get_instantaneous_values()
            if not sma_data_raw:
                raise UpdateFailed("No data received from SMA API")
            
            _LOGGER.debug(f"Datos PULL de SMA recibidos: {sma_data_raw}")

        except SmaApiError as err:
            raise UpdateFailed(f"Error communicating with SMA API: {err}")
        
        # --- PASO 2: PUSH (Enviar datos a Spock Cloud) ---
        try:
            await self._async_push_to_spock(sma_data_raw)
        except Exception as e:
            # Es importante no fallar el PULL si el PUSH falla.
            # Solo registramos el error.
            _LOGGER.error(f"Error al hacer PUSH de telemetría a Spock: {e}")

        # Devolvemos los datos crudos de SMA para los sensores locales
        return sma_data_raw

    def _map_sma_to_spock(self, sma_data: dict) -> dict:
        """
        Función de mapeo.
        Transforma las claves de SMA a las claves que tu API de Spock espera.
        Incluye lógica para promediar voltajes y corrientes trifásicos.
        """
        
        def get_avg_or_single(base_key: str) -> Optional[float]:
            """
            Calcula el promedio si hay L1, L2, L3, o devuelve L1 si es monofásico.
            base_key debe ser "Measurement.Grid.V" o "Measurement.Grid.A"
            """
            keys = [f"{base_key}.L1", f"{base_key}.L2", f"{base_key}.L3"]
            values = []
            
            for key in keys:
                val = sma_data.get(key)
                if isinstance(val, (int, float)):
                    values.append(val)
            
            if not values:
                return None
            
            # Devuelve el promedio de las fases encontradas
            return sum(values) / len(values)

        # --- Fin de la función helper ---

        avg_grid_voltage = get_avg_or_single("Measurement.Grid.V")
        avg_grid_current = get_avg_or_single("Measurement.Grid.A")

        # Mapeo de SMA a Spock
        spock_payload = {
            # Batería
            "battery_soc": sma_data.get("Measurement.Bat.ChaStt"),
            "battery_power": sma_data.get("Measurement.Bat.P"),
            "battery_voltage": sma_data.get("Measurement.Bat.V"),
            "battery_current": sma_data.get("Measurement.Bat.A"),
            "battery_temperature": sma_data.get("Measurement.Bat.Temp"),
            
            # Potencias
            "grid_power": sma_data.get("Measurement.Grid.P"),
            "pv_power": sma_data.get("Measurement.Pv.P"),
            "load_power": sma_data.get("Measurement.Consumption.P"),
            
            # Red (Valores calculados)
            "grid_voltage": avg_grid_voltage,
            "grid_current": avg_grid_current,
            "grid_frequency": sma_data.get("Measurement.Grid.F"),
        }
        
        # Filtra valores nulos (None)
        return {k: v for k, v in spock_payload.items() if v is not None}


    async def _async_push_to_spock(self, sma_data_raw: dict):
        """Envía la telemetría formateada a la API de Spock."""
        
        spock_data = self._map_sma_to_spock(sma_data_raw)
        
        spock_data["plant_id"] = self._plant_id
        
        _LOGGER.debug(f"Haciendo PUSH a {self._spock_api_url} con payload: {spock_data}")
        
        try:
            async with async_timeout.timeout(10):
                response = await self._session.post(
                    self._spock_api_url,
                    json=spock_data,
                    headers=self._headers,
                )
                response.raise_for_status()
                _LOGGER.debug(f"PUSH a Spock exitoso (Status: {response.status})")

        except ClientError as e:
            _LOGGER.warning(f"Error de red en PUSH a Spock: {e}")
        except Exception as e:
            _LOGGER.error(f"Error inesperado en PUSH a Spock: {e}")
            raise
