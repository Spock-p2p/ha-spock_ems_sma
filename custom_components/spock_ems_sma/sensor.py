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
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfFrequency,
    UnitOfTemperature,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# --- MAPEO DE SENSORES LOCALES ---
# Claves de PYSMA que queremos exponer como sensores en HA
# (Las claves deben coincidir con las de pysma, ej: "grid_power")
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
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    sensors = []
    for pysma_key, config in SENSOR_MAP.items():
        # Solo añade el sensor si la clave existe en el primer refresh
        if pysma_key in coordinator.data:
            sensors.append(
                SpockSmaSensor(
                    coordinator=coordinator,
                    entry_id=entry.entry_id,
                    pysma_key=pysma_key,
                    config=config,
                )
            )
        else:
            _LOGGER.debug(f"Sensor '{pysma_key}' no encontrado en datos de SMA, se omitirá.")
    
    async_add_entities(sensors)

class SpockSmaSensor(CoordinatorEntity, SensorEntity):
    """Sensor que lee datos del Coordinador de telemetría SMA."""

    def __init__(self, coordinator, entry_id, pysma_key, config):
        super().__init__(coordinator)
        self._data_key = pysma_key
        
        # Atributos de la entidad
        self._attr_name = config["name"]
        self._attr_native_unit_of_measurement = config.get("unit")
        self._attr_device_class = config.get("device_class")
        self._attr_state_class = config.get("state_class")
        self._attr_unique_id = f"{entry_id}_{pysma_key}"
        
        # (Opcional) Enlazar entidad a un dispositivo
        # self._attr_device_info = ... 

    @property
    def native_value(self):
        """Retorna el valor del sensor desde el coordinador."""
        if self.coordinator.data:
            return self.coordinator.data.get(self._data_key)
        return None
