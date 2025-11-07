import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, MASTER_SWITCH_KEY, MASTER_SWITCH_NAME
from .coordinator import SmaTelemetryCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Configura el interruptor maestro."""
    
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    async_add_entities([
        SpockSmaMasterSwitch(coordinator, entry.entry_id)
    ])

class SpockSmaMasterSwitch(SwitchEntity, RestoreEntity):
    """
    Representa el interruptor maestro que habilita/deshabilita
    el polling y el push del coordinador.
    """

    def __init__(self, coordinator: SmaTelemetryCoordinator, entry_id: str):
        """Inicializa el switch."""
        self.coordinator = coordinator
        
        # Atributos de la entidad
        self._attr_unique_id = f"{entry_id}_{MASTER_SWITCH_KEY}"
        self._attr_name = MASTER_SWITCH_NAME
        self._attr_icon = "mdi:engine" # Icono de "motor"
        
        # El estado del switch (self._attr_is_on) se sincronizará
        # con el estado del coordinador (self.coordinator.polling_enabled)
        # en async_added_to_hass.

    @property
    def is_on(self) -> bool:
        """Devuelve el estado actual del coordinador."""
        return self.coordinator.polling_enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Activa la operativa (polling/push)."""
        _LOGGER.info("Activando operativa global de Spock EMS (SMA)")
        self.coordinator.polling_enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Desactiva la operativa (polling/push)."""
        _LOGGER.info("Desactivando operativa global de Spock EMS (SMA)")
        self.coordinator.polling_enabled = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """
        Se llama cuando la entidad se añade a HA.
        Restaura el estado anterior del switch.
        """
        await super().async_added_to_hass()
        
        # Restaura el estado desde el 'recorder'
        last_state = await self.async_get_last_state()
        
        if last_state and last_state.state == "off":
            self.coordinator.polling_enabled = False
        else:
            # Por defecto (o si estaba 'on'), lo dejamos 'on'
            self.coordinator.polling_enabled = True
            
        _LOGGER.debug(f"Estado restaurado del switch maestro: {'ON' if self.coordinator.polling_enabled else 'OFF'}")
        
        # Sincroniza el estado de HA con el estado del coordinador
        self.async_write_ha_state()
