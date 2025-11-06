"""Switch para habilitar/deshabilitar el sondeo de Spock EMS SMA."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN # , CONF_BATTERY_IP (No es necesaria aquí)
from . import SpockEnergyCoordinator 

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configura el interruptor desde la entrada de configuración."""
    
    coordinator: SpockEnergyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([SpockEmsSwitch(hass, entry, coordinator)])


class SpockEmsSwitch(CoordinatorEntity[SpockEnergyCoordinator], SwitchEntity):
    """Interruptor para controlar el sondeo de la API/Modbus."""

    _attr_has_entity_name = True
    _attr_translation_key = "polling_enabled"
    _attr_icon = "mdi:link-box-variant" 

    def __init__(
        self, 
        hass: HomeAssistant, 
        entry: ConfigEntry, 
        coordinator: SpockEnergyCoordinator
    ) -> None:
        """Inicializa el interruptor."""
        super().__init__(coordinator) 
        self.hass = hass
        self._entry_id = entry.entry_id
        
        self._attr_unique_id = f"{self._entry_id}_polling_enabled"
        
        # --- CORRECCIÓN (Línea 52 aprox) ---
        # Cambiamos 'coordinator.modbus_ip' por 'coordinator.battery_ip'
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=f"Spock EMS SMA ({coordinator.battery_ip})",
            manufacturer="Spock/SMA",
            model="Modbus EMS Control",
        )
        # --- FIN DE LA CORRECCIÓN ---

    @property
    def is_on(self) -> bool:
        """Devuelve true si el sondeo está habilitado."""
        return self.hass.data[DOMAIN].get(self._entry_id, {}).get("is_enabled", True)

    async def async_turn_on(self, **kwargs) -> None:
        """Habilita el sondeo."""
        _LOGGER.debug("Habilitando sondeo Modbus/API")
        self.hass.data[DOMAIN][self._entry_id]["is_enabled"] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Deshabilita el sondeo."""
        _LOGGER.debug("Deshabilitando sondeo Modbus/API")
        self.hass.data[DOMAIN][self._entry_id]["is_enabled"] = False
        self.async_write_ha_state()
        
    @callback
    def _handle_coordinator_update(self) -> None:
        """Maneja las actualizaciones del coordinador."""
        self.async_write_ha_state()
