import logging
import voluptuous as vol
from aiohttp import ClientError

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
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
    CONF_MODBUS_UNIT_ID,
)

_LOGGER = logging.getLogger(__name__)

# ----- ESQUEMA INICIAL (AL AÑADIR LA INTEGRACIÓN) -----
DATA_SCHEMA = vol.Schema(
    {
        # --- Spock ---
        vol.Required(CONF_PLANT_ID): str,
        vol.Required(CONF_SPOCK_API_TOKEN): str,
        # --- SMA Webconnect ---
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_GROUP, default=DEFAULT_GROUP): vol.In(GROUPS),
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SSL, default=True): bool,
        # --- Modbus (solo unit_id; puerto = 502 hardcoded) ---
        vol.Optional(CONF_MODBUS_UNIT_ID, default=3): int,
    }
)


async def validate_input(hass, data: dict):
    """Valida la conexión con SMA usando pysma."""
    protocol = "https" if data[CONF_SSL] else "http"
    url = f"{protocol}://{data[CONF_HOST]}"

    _LOGGER.debug("Creando sesión de aiohttp con verify_ssl=False (Hardcoded)")
    session = async_get_clientsession(hass, verify_ssl=False)

    sma = SMAWebConnect(
        session=session,
        url=url,
        password=data[CONF_PASSWORD],
        group=data[CONF_GROUP],
    )

    await sma.new_session()
    device_info = await sma.device_info()
    await sma.close_session()

    return {"title": data[CONF_HOST], "serial": device_info.serial}


class SmaSpockConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Flujo de configuración para Spock EMS SMA."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Obtiene el flujo de opciones para reconfigurar."""
        return SmaSpockOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Maneja el paso de configuración inicial del usuario."""
        errors = {}

        if user_input is not None:
            try:
                _LOGGER.info("Probando conexión con SMA en %s", user_input[CONF_HOST])
                info = await validate_input(self.hass, user_input)
                _LOGGER.info(
                    "Conexión con SMA exitosa. Serial: %s",
                    info["serial"],
                )

                await self.async_set_unique_id(info["serial"])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

            except SmaAuthenticationException:
                _LOGGER.warning("Falló la validación de SMA: Autenticación inválida")
                errors["base"] = "invalid_auth"
            except (SmaConnectionException, ClientError, TimeoutError):
                _LOGGER.warning("Falló la validación de SMA: No se puede conectar")
                errors["base"] = "cannot_connect"
            except Exception as e:
                _LOGGER.error(
                    "Error desconocido en validación de SMA: %s", e, exc_info=True
                )
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )


class SmaSpockOptionsFlow(config_entries.OptionsFlow):
    """
    Maneja el flujo de opciones (reconfiguración).
    Esto permite al usuario editar IP, token, unit_id, etc.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Inicializa el flujo de opciones."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Maneja el paso inicial del flujo de opciones."""
        errors = {}

        data = self.config_entry.data

        if user_input is not None:
            try:
                _LOGGER.info(
                    "Reconfigurando. Probando nueva conexión con SMA en %s",
                    user_input[CONF_HOST],
                )
                await validate_input(self.hass, user_input)
                _LOGGER.info("Validación de reconfiguración exitosa.")

                # Guardamos TODO (incluyendo modbus_unit_id) en config_entry.data
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=user_input,
                )

                # Recargamos la integración
                await self.hass.config_entries.async_reload(
                    self.config_entry.entry_id
                )

                return self.async_create_entry(title="", data={})

            except SmaAuthenticationException:
                errors["base"] = "invalid_auth"
            except (SmaConnectionException, ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception as e:
                _LOGGER.error(
                    "Error desconocido en reconfiguración: %s", e, exc_info=True
                )
                errors["base"] = "unknown"

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_PLANT_ID, default=data.get(CONF_PLANT_ID)
                ): str,
                vol.Required(
                    CONF_SPOCK_API_TOKEN, default=data.get(CONF_SPOCK_API_TOKEN)
                ): str,
                vol.Required(CONF_HOST, default=data.get(CONF_HOST)): str,
                vol.Optional(
                    CONF_GROUP,
                    default=data.get(CONF_GROUP, DEFAULT_GROUP),
                ): vol.In(GROUPS),
                vol.Required(
                    CONF_PASSWORD, default=data.get(CONF_PASSWORD)
                ): str,
                vol.Optional(CONF_SSL, default=data.get(CONF_SSL, True)): bool,
                vol.Optional(
                    CONF_MODBUS_UNIT_ID,
                    default=data.get(CONF_MODBUS_UNIT_ID, 3),
                ): int,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
        )
