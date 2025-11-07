import voluptuous as vol
from aiohttp.client_exceptions import ClientError
import logging

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_SPOCK_API_TOKEN,
    CONF_PLANT_ID,
    SMA_DEFAULT_USERNAME,
)
from .sma_api import SmaApiClient, SmaApiError  # Importamos el nuevo cliente SMA

_LOGGER = logging.getLogger(__name__)

# Schema de Configuración
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME, default=SMA_DEFAULT_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_PLANT_ID): str,
        vol.Required(CONF_SPOCK_API_TOKEN): str,
    }
)

class SmaSpockConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Flujo de configuración para Spock EMS SMA."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Maneja el paso de configuración inicial del usuario."""
        errors = {}

        if user_input is not None:
            try:
                # Validar la conexión con SMA
                session = async_get_clientsession(self.hass)
                client = SmaApiClient(
                    host=user_input[CONF_HOST],
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    session=session,
                )
                
                _LOGGER.info(f"Probando conexión con SMA en {user_input[CONF_HOST]}")
                await client.test_connection()
                _LOGGER.info("Conexión con SMA exitosa.")

            except SmaApiError:
                _LOGGER.warning("Falló la validación de SMA: Autenticación inválida")
                errors["base"] = "invalid_auth"
            except (ClientError, TimeoutError):
                _LOGGER.warning("Falló la validación de SMA: No se puede conectar")
                errors["base"] = "cannot_connect"
            except Exception as e:
                _LOGGER.error(f"Error desconocido en validación de SMA: {e}")
                errors["base"] = "unknown"
            
            # Si no hay errores, crea la entrada
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_HOST], data=user_input
                )

        # Muestra el formulario (o lo vuelve a mostrar con errores)
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )
