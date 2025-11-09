import logging
import voluptuous as vol
from aiohttp import ClientError
# import ssl (ya no se usa)
# from aiohttp import TCPConnector (ya no se usa)

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
)
# from homeassistant.core import callback (no se usa)
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
    
    # --- ¡CORRECCIÓN! ---
    # La forma correcta y no-bloqueante de obtener una sesión
    # que no verifica SSL (hardcoded).
    _LOGGER.debug("Creando sesión de aiohttp con verify_ssl=False (Hardcoded)")
    session = async_get_clientsession(hass, verify_ssl=False)
    # --- FIN DE LA CORRECCIÓN ---
    
    sma = SMAWebConnect(
        session=session,
        url=url,
        password=data[CONF_PASSWORD],
        group=data[CONF_GROUP]
    )
    
    # Intenta iniciar sesión y obtener info
    # Nota: La sesión no se cierra aquí, pysma la reutilizará
    await sma.new_session()
    device_info = await sma.device_info()
    
    # Cerramos la sesión de validación explícitamente
    await sma.close_session()
    
    return {"title": data[CONF_HOST], "serial": device_info.serial}


class SmaSpockConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Flujo de configuración para Spock EMS SMA."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Maneja el paso de configuración inicial del usuario."""
        errors = {}

        if user_input is not None:
            try:
                _LOGGER.info(f"Probando conexión con SMA en {user_input[CONF_HOST]}")
                info = await validate_input(self.hass, user_input)
                _LOGGER.info(f"Conexión con SMA exitosa. Serial: {info['serial']}")
                
                await self.async_set_unique_id(info["serial"])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)

            except SmaAuthenticationException:
                _LOGGER.warning("Falló la validación de SMA: Autenticación inválida")
                errors["base"] = "invalid_auth"
            except (SmaConnectionException, ClientError, TimeoutError):
                _LOGGER.warning("Falló la validación de SMA: No se puede conectar")
                errors["base"] = "cannot_connect"
            except Exception as e:
                _LOGGER.error(f"Error desconocido en validación de SMA: {e}", exc_info=True)
                errors["base"] = "unknown"
            
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )
