import logging
import voluptuous as vol
from aiohttp.web import Response

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SPOCK_COMMAND_API_PATH

_LOGGER = logging.getLogger(__name__)

# Schema de los comandos que esperas RECIBIR
COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Required("command"): cv.string,
        vol.Optional("value"): vol.Coerce(float),
    }
)

class SpockApiView(HomeAssistantView):
    """
    Vista de API (INBOUND) para recibir comandos de Spock Cloud.
    Valida el token de autorización y el 'plant_id'.
    """
    
    url = SPOCK_COMMAND_API_PATH  # "/api/spock_ems_sma"
    name = "api:spock_ems_sma"
    requires_auth = False  # Usamos validación de token propia

    def __init__(self, hass: HomeAssistant, entry_id: str, api_token: str, plant_id: str):
        self.hass = hass
        self.entry_id = entry_id
        self.valid_token = f"Bearer {api_token}"
        self.valid_plant_id = plant_id
        # (Fase 2) Aquí se instanciará el cliente Pysma para escritura

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
            # --- Aquí irá la lógica de FASE 2 (pysma) ---
            _LOGGER.info(f"Fase 1: Comando '{command}' recibido (pysma pendiente).")
            
            return Response(text="Command received (Phase 1)", status=200)

        except Exception as e:
            _LOGGER.error(f"Error al ejecutar comando '{command}': {e}")
            return Response(text=f"Error executing command: {e}", status=500)
