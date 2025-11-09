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

# --- ¡MAPEO DE SENSORES CORREGIDO! ---
# Hemos cambiado los sensores de 'grid_power' (inversor)
# por los de 'metering' (contador)
SENSOR_MAP = {
    # Batería (Estos estaban bien)
    "battery_soc_total": {
        "name": "SMA Batería SOC",
        "unit": PERCENTAGE,
        "device_class": SensorDeviceClass.BATTERY,
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
    "battery_temp_a": {
        "name": "SMA Batería Temperatura",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    
    # PV (Estos estaban bien)
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
    
    # Red (Contador) - ¡ESTOS SON LOS NUEVOS!
    "metering_power_absorbed": {
        "name": "SMA Potencia Red (Importación)",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "metering_power_supplied": {
        "name": "SMA Potencia Red (Exportación)",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },

    # Estado (Estaba bien)
    "status": {
        "name": "SMA Estado",
        "unit": None,
        "device_class": None,
        "state_class": None,
    },
    
    # SENSORES ANTIGUOS ELIMINADOS (porque daban 0 o 'Desconocido'):
    # "grid_power": ...
    # "metering_current_consumption": ...
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
    # Usamos los datos del primer refresh (coordinator.data) para ver qué sensores crear
    if coordinator.data:
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
                _LOGGER.debug(f"Sensor '{pysma_key}' no encontrado en datos de SMA, se omitirá.")
    
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
        
        if self._data_key == "status":
            return value
        
        # Forzamos todos los demás valores a float
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
