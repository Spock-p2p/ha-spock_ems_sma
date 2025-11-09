import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity
from .const import DOMAIN, MASTER_SWITCH_KEY, MASTER_SWITCH_NAME
from .coordinator import SmaTelemetryCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Configura el interruptor maestro."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([SpockSmaMasterSwitch(coordinator, entry.entry_id)])

class SpockSmaMasterSwitch(SwitchEntity, RestoreEntity):
    """Interruptor maestro para habilitar/deshabilitar la operativa."""

    def __init__(self, coordinator: SmaTelemetryCoordinator, entry_id: str):
        self.coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_{MASTER_SWITCH_KEY}"
        self._attr_name = MASTER_SWITCH_NAME
        self._attr_icon = "mdi:engine"

    @property
    def is_on(self) -> bool:
        return self.coordinator.polling_enabled

    async def async_turn_on(self, **kwargs) -> None:
        _LOGGER.info("Activando operativa Spock EMS (SMA)")
        self.coordinator.polling_enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        _LOGGER.info("Desactivando operativa Spock EMS (SMA)")
        self.coordinator.polling_enabled = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state == "off":
            self.coordinator.polling_enabled = False
        else:
            self.coordinator.polling_enabled = True
        self.async_write_ha_state()
