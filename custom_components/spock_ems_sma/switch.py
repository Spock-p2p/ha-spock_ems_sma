import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity
# Importamos DeviceInfo para el type hint
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MASTER_SWITCH_KEY, MASTER_SWITCH_NAME
from .coordinator import SmaTelemetryCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Configura el interruptor maestro."""
    
    coordinator: SmaTelemetryCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    # --- NUEVO: Creamos el objeto DeviceInfo ---
    sma_device = coordinator.sma_device_info
    device_info = DeviceInfo(
        identifiers={(DOMAIN, sma_device.serial)},
        name=sma_device.name,
        manufacturer=sma_device.manufacturer,
        model=sma_device.type,
        sw_version=sma_device.sw_version,
    )
    # --- Fin ---
    
    async_add_entities([
        SpockSmaMasterSwitch(coordinator, entry.entry_id, device_info) # <-- Pasamos el device_info
    ])

class SpockSmaMasterSwitch(SwitchEntity, RestoreEntity):
    """
    Representa el interruptor maestro que habilita/deshabilita
    el polling y el push del coordinador.
    """

    def __init__(
        self, 
        coordinator: SmaTelemetryCoordinator, 
        entry_id: str,
        device_info: DeviceInfo # <-- Recibimos el device_info
    ):
        """Inicializa el switch."""
        self.coordinator = coordinator
        
        # Atributos de la entidad
        self._attr_unique_id = f"{entry_id}_{MASTER_SWITCH_KEY}"
        self._attr_name = MASTER_SWITCH_NAME
        self._attr_icon = "mdi:engine"
        
        # --- NUEVO: Asignamos la entidad a un dispositivo ---
        self._attr_device_info = device_info

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
        """Restaura el estado anterior del switch."""
        await super().async_added_to_hass()
        
        last_state = await self.async_get_last_state()
        
        if last_state and last_state.state == "off":
            self.coordinator.polling_enabled = False
        else:
            self.coordinator.polling_enabled = True
            
        _LOGGER.debug(f"Estado restaurado del switch maestro: {'ON' if self.coordinator.polling_enabled else 'OFF'}")
        
        self.async_write_ha_state()
