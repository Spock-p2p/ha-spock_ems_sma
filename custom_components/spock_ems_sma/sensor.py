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
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .coordinator import SmaTelemetryCoordinator 

_LOGGER = logging.getLogger(__name__)

# --- SENSOR_MAP (sin cambios) ---
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
    
    sma_device = coordinator.sma_device_info
    device_info = DeviceInfo(
        identifiers={(DOMAIN, sma_device.serial)},
        name=sma_device.name,
        manufacturer=sma_device.manufacturer,
        model=sma_device.type,
        sw_version=sma_device.sw_version,
    )

    sensors = []
    for pysma_key, config in SENSOR_MAP.items():
        if pysma_key in coordinator.data:
            sensors.append(
                SpockSmaSensor(
                    coordinator=coordinator,
                    entry_id=entry.entry_id,
                    pysma_key=pysma_key,
                    config=config,
                    device_info=device_info
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
        device_info: DeviceInfo
    ):
        super().__init__(coordinator)
        self._data_key = pysma_key
        
        # Atributos de la entidad
        self._attr_name = config["name"]
        self._attr_native_unit_of_measurement = config.get("unit")
        self._attr_device_class = config.get("device_class")
        self._attr_state_class = config.get("state_class")
        self._attr_unique_id = f"{entry_id}_{pysma_key}"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Retorna el valor del sensor como un float (o string para 'status')."""
        if not self.coordinator.data:
            return None
        
        value = self.coordinator.data.get(self._data_key)
        
        if value is None:
            return None
        
        # --- ¡LA SOLUCIÓN! ---
        
        # El sensor 'status' es un string, lo devolvemos tal cual.
        if self._data_key == "status":
            return value
        
        # Forzamos todos los demás valores a float.
        # Los sensores de Potencia/Batería de HA fallan en la UI si reciben un integer.
        try:
            return float(value)
        except (ValueError, TypeError):
            # Si el valor es algo inesperado (ej. "N/A"), devuelve None
            return None
