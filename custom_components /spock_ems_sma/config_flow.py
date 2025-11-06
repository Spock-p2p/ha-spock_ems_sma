"""Config flow para Spock EMS Modbus."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_API_TOKEN,
    CONF_PLANT_ID,
    CONF_MODBUS_IP,
    CONF_MODBUS_PORT,
    CONF_MODBUS_SLAVE,
    DEFAULT_MODBUS_PORT,
    DEFAULT_MODBUS_SLAVE,
)

_LOGGER = logging.getLogger(__name__)


class SpockEmsModbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Maneja el flujo de configuración."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Paso inicial de configuración."""
        errors: dict[str, str] = {}
        if user_input is not None:
            
            # (No se valida la API aquí, se validará en el primer ciclo)
            
            await self.async_set_unique_id(f"{user_input[CONF_MODBUS_IP]}-{user_input[CONF_PLANT_ID]}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Spock EMS Modbus ({user_input[CONF_MODBUS_IP]})",
                data=user_input,
            )

        STEP_USER_DATA_SCHEMA = vol.Schema(
            {
                vol.Required(CONF_API_TOKEN): str,
                vol.Required(CONF_PLANT_ID): int,
                vol.Required(CONF_MODBUS_IP): str,
                vol.Optional(CONF_MODBUS_PORT, default=DEFAULT_MODBUS_PORT): int,
                vol.Optional(CONF_MODBUS_SLAVE, default=DEFAULT_MODBUS_SLAVE): int,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowHandler:
        """Obtiene el flujo de opciones para esta entrada."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    """Maneja el flujo de opciones (reconfiguración)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Inicializa."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Maneja el paso inicial del flujo de opciones."""
        
        if user_input is not None:
            # Actualiza el unique_id si la IP o Plant ID cambian
            new_unique_id = f"{user_input[CONF_MODBUS_IP]}-{user_input[CONF_PLANT_ID]}"
            if self.config_entry.unique_id != new_unique_id:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, unique_id=new_unique_id
                )
            return self.async_create_entry(title="", data=user_input)

        current_config = {**self.config_entry.data, **self.config_entry.options}

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_API_TOKEN,
                    default=current_config.get(CONF_API_TOKEN),
                ): str,
                vol.Required(
                    CONF_PLANT_ID,
                    default=current_config.get(CONF_PLANT_ID),
                ): int,
                vol.Required(
                    CONF_MODBUS_IP,
                    default=current_config.get(CONF_MODBUS_IP),
                ): str,
                vol.Optional(
                    CONF_MODBUS_PORT,
                    default=current_config.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT)
                ): int,
                vol.Optional(
                    CONF_MODBUS_SLAVE,
                    default=current_config.get(CONF_MODBUS_SLAVE, DEFAULT_MODBUS_SLAVE)
                ): int,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema
        )
