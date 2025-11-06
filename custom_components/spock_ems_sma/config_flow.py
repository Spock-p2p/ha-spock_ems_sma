"""Config flow para Spock EMS SMA."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_PASSWORD

from .const import (
    DOMAIN,
    CONF_API_TOKEN,
    CONF_PLANT_ID,
    CONF_BATTERY_IP,
    CONF_BATTERY_PORT,
    CONF_BATTERY_SLAVE,
    CONF_PV_IP,
    CONF_PV_PORT,
    CONF_PV_SLAVE,
    DEFAULT_MODBUS_PORT,
    DEFAULT_MODBUS_SLAVE,
    # --- CAMBIO ---
    CONF_SHM_IP,
    CONF_SHM_GROUP,
    CONF_SHM_PASSWORD,
    DEFAULT_SHM_GROUP,
    # --- FIN CAMBIO ---
)

_LOGGER = logging.getLogger(__name__)


class SpockEmsSmaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Maneja el flujo de configuración."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Paso inicial de configuración."""
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_BATTERY_IP]}-{user_input[CONF_PLANT_ID]}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Spock EMS SMA ({user_input[CONF_BATTERY_IP]})",
                data=user_input,
            )
        
        # --- CAMBIO: Añadidos campos opcionales de SHM ---
        STEP_USER_DATA_SCHEMA = vol.Schema(
            {
                vol.Required(CONF_API_TOKEN): str,
                vol.Required(CONF_PLANT_ID): int,
                vol.Required(CONF_BATTERY_IP): str,
                vol.Optional(CONF_BATTERY_PORT, default=DEFAULT_MODBUS_PORT): int,
                vol.Optional(CONF_BATTERY_SLAVE, default=DEFAULT_MODBUS_SLAVE): int,
                vol.Required(CONF_PV_IP): str, 
                vol.Optional(CONF_PV_PORT, default=DEFAULT_MODBUS_PORT): int,
                vol.Optional(CONF_PV_SLAVE, default=DEFAULT_MODBUS_SLAVE): int,
                # --- Campos Speedwire (Opcionales) ---
                vol.Optional(CONF_SHM_IP): str,
                vol.Optional(CONF_SHM_GROUP, default=DEFAULT_SHM_GROUP): vol.In(["user", "installer"]),
                vol.Optional(CONF_SHM_PASSWORD): str,
            }
        )
        # --- FIN CAMBIO ---

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA
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
            new_unique_id = f"{user_input[CONF_BATTERY_IP]}-{user_input[CONF_PLANT_ID]}"
            if self.config_entry.unique_id != new_unique_id:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, unique_id=new_unique_id
                )
            return self.async_create_entry(title="", data=user_input)

        current_config = {**self.config_entry.data, **self.config_entry.options}
        
        # --- CAMBIO: Añadidos campos opcionales de SHM ---
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
                    CONF_BATTERY_IP,
                    default=current_config.get(CONF_BATTERY_IP),
                ): str,
                vol.Optional(
                    CONF_BATTERY_PORT,
                    default=current_config.get(CONF_BATTERY_PORT, DEFAULT_MODBUS_PORT)
                ): int,
                vol.Optional(
                    CONF_BATTERY_SLAVE,
                    default=current_config.get(CONF_BATTERY_SLAVE, DEFAULT_MODBUS_SLAVE)
                ): int,
                vol.Required(
                    CONF_PV_IP,
                    default=current_config.get(CONF_PV_IP)
                ): str,
                vol.Optional(
                    CONF_PV_PORT,
                    default=current_config.get(CONF_PV_PORT, DEFAULT_MODBUS_PORT)
                ): int,
                vol.Optional(
                    CONF_PV_SLAVE,
                    default=current_config.get(CONF_PV_SLAVE, DEFAULT_MODBUS_SLAVE)
                ): int,
                # --- Campos Speedwire (Opcionales) ---
                vol.Optional(
                    CONF_SHM_IP,
                    default=current_config.get(CONF_SHM_IP, "")
                ): str,
                vol.Optional(
                    CONF_SHM_GROUP,
                    default=current_config.get(CONF_SHM_GROUP, DEFAULT_SHM_GROUP)
                ): vol.In(["user", "installer"]),
                vol.Optional(
                    CONF_SHM_PASSWORD,
                    default=current_config.get(CONF_SHM_PASSWORD, "")
                ): str,
            }
        )
        # --- FIN CAMBIO ---

        return self.async_show_form(
            step_id="init", data_schema=options_schema
        )
