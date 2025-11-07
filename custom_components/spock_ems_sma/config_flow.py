import logging
import voluptuous as vol
from aiohttp import ClientError, TCPConnector
import ssl

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_SSL,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from pysma import SMAWebConnect, SmaAuthenticationException, SmaConnectionException

from .const import (
    DOMAIN,
    CONF_SPOCK_API_TOKEN,
    CONF_PLANT_ID,
    CONF_GROUP,
    GROUPS,
    DEFAULT_GROUP,
)

_LOGGER = logging.getLogger(__name__)

# Schema de Configuración (Reordenado y sin 'verify_ssl')
DATA_SCHEMA = vol.Schema(
    {
        # --- Spock (Primero) ---
        vol.Required(CONF_PLANT_ID): str,
        vol.Required(CONF_SPOCK_API_TOKEN): str,
        # --- SMA (Después) ---
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_GROUP, default=DEFAULT_GROUP): vol.In(GROUPS),
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SSL, default=True): bool,
    }
)

async def validate_input(hass, data: dict):
    """Valida la conexión con SMA usando pysma."""
    
    protocol = "https" if data[CONF_SSL] else "http"
    url = f"{protocol}://{data[CONF_HOST]}"
    
    connector_args = {}
    if data[CONF_SSL]:
        # --- LÓGICA HARDCODED ---
        # Siempre usamos un contexto SSL que NO verifica el certificado
        _LOGGER.debug("Usando SSL sin verificación (Hardcoded)")
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector_args["ssl"] = ssl_context
    
    connector = TCPConnector(**connector_args)
    # Creamos una sesión nueva para la validación
    # Usamos la sesión de HA, pero con nuestro conector
    session = async_get_clientsession(hass, connector=connector)
    
    sma = SMAWebConnect(
        session=session,
        url=url,
        password=data[CONF_PASSWORD],
