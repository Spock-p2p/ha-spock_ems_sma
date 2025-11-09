import logging
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfPower,
    PERCENTAGE,
    UnitOfTemperature,
)
# Importamos DeviceInfo para el type hint
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .coordinator import SmaTelemetryCoordinator # Importamos el coordinador

_LOGGER = logging.getLogger(__name__)

# ... (SENSOR_MAP sigue igual que antes) ...
SENSOR_MAP = {
    "battery_soc_total": {
        "name": "SMA Batería SOC",
        "unit": PERCENTAGE,
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "grid_power": {
        "name": "SMA Potencia Red",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "pv_power_a": {
        "name": "SMA PV Potencia A",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "pv_power_b": {
        "name": "SMA PV Potencia B",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_power_charge_total": {
        "name": "SMA Batería Potencia Carga",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_power_discharge_total": {
        "name": "SMA Batería Potencia Descarga",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "metering_current_consumption": {
        "name": "SMA Consumo Potencia",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_temp_a": {
        "name": "SMA Batería Temperatura",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "status": {
        "name": "SMA Estado",
        "unit": None,
        "device_class": None,
        "state_class": None,
    },
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Configura los sensores desde la config entry."""
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

    sensors = []
    for pysma_key, config in SENSOR_MAP.items():
        if pysma_key in coordinator.data:
            sensors.append(
                SpockSmaSensor(
                    coordinator=coordinator,
                    entry_id=entry.entry_id,
                    pysma_key=pysma_key,
                    config=config,
                    device_info=device_info # <-- Pasamos el device_info
                )
            )
        else:
            _LOGGER.debug(f"Sensor '{pysma_key}' no encontrado, se omitirá.")
    
    async_add_entities(sensors)

class SpockSmaSensor(CoordinatorEntity, SensorEntity):
    """Sensor que lee datos del Coordinador de telemetría SMA."""

    def __init__(
        self, 
        coordinator: SmaTelemetryCoordinator, 
        entry_id: str, 
        pysma_key: str, 
        config: dict,
        device_info: DeviceInfo # <-- Recibimos el device_info
    ):
        super().__init__(coordinator)
        self._data_key = pysma_key
        
        # Atributos de la entidad
        self._attr_name = config["name"]
        self._attr_native_unit_of_measurement = config.get("unit")
        self._attr_device_class = config.get("device_class")
        self._attr_state_class = config.get("state_class")
        self._attr_unique_id = f"{entry_id}_{pysma_key}"
        
        # --- NUEVO: Asignamos la entidad a un dispositivo ---
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Retorna el valor del sensor desde el coordinador."""
        if self.coordinator.data:
            return self.coordinator.data.get(self._data_key)
        return None
