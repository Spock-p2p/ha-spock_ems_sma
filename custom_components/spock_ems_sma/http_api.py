import logging
import voluptuous as vol
from aiohttp.web import Response

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from pysma import SMAWebConnect # Importado para Fase 2

from .const import DOMAIN, SPOCK_COMMAND_API_PATH

_LOGGER = logging.getLogger(__name__)

# Schema de los comandos que esperas RECIBIR
COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Required("command"): cv.string,
        vol.Optional("value"): cv.Coerce(float),
    }
)

class SpockApiView(HomeAssistantView):
    """
    Vista de API (INBOUND) para recibir comandos de Spock Cloud.
    """
    
    url = SPOCK_COMMAND_API_PATH
    name = f"api:{DOMAIN}"
    requires_auth = False  # Usamos validación de token propia

    def __init__(
        self, 
        hass: HomeAssistant, 
        entry_id: str, 
        api_token: str, 
        plant_id: str,
        pysma_api: SMAWebConnect
    ):
        self.hass = hass
        self.entry_id = entry_id
        self.valid_token = f"Bearer {api_token}"
        self.valid_plant_id = plant_id
        self.pysma_api = pysma_api # Guardamos para Fase 2

    async def post(self, request):
        """Maneja las peticiones POST de comandos."""
        
        # 1. Validar Token
        auth_header = request.headers.get("Authorization")
        if auth_header != self.valid_token:
            _LOGGER.warning("Rechazada petición (INBOUND): Token inválido")
            return Response(text="Invalid token", status=401)

        try:
            data = await request.json()
            data = COMMAND_SCHEMA(data)
        except Exception as e:
            _LOGGER.error(f"Error al parsear JSON (INBOUND): {e}")
            return Response(text=f"Invalid JSON: {e}", status=400)

        # 2. Validar Plant ID
        received_plant_id = data.get("plant_id")
        if received_plant_id != self.valid_plant_id:
            _LOGGER.warning(
                f"Rechazada petición (INBOUND): Plant ID no coincide. Recibido: {received_plant_id}"
            )
            return Response(text="Invalid plant_id", status=403)
        
        # 3. Procesar el Comando
        command = data.get("command")
        value = data.get("value")
        _LOGGER.info(
            f"Comando (INBOUND) recibido para plant_id {received_plant_id}: {command} = {value}"
        )

        try:
            # --- Aquí irá la lógica de FASE 2 ---
            # Ejemplo de cómo se haría:
            # if command == "set_algo":
            #     await self.pysma_api.set_parameter(sensor_de_pysma, value)
            
            _LOGGER.info(f"Fase 1: Comando '{command}' recibido (pysma pendiente).")
            
            return Response(text="Command received (Phase 1)", status=200)

        except Exception as e:
            _LOGGER.error(f"Error al ejecutar comando '{command}': {e}")
            return Response(text=f"Error executing command: {e}", status=500)
