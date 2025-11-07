import logging
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfPower,
    UnitOfEnergy,
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfFrequency,
    UnitOfTemperature,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# --- MAPEO DE SENSORES LOCALES ---
# Define los sensores que se crearán en Home Assistant
# Las claves ('key') deben coincidir con las del diccionario de SMA
SENSOR_MAP = {
    "battery_soc": {
        "key": "Measurement.Bat.ChaStt",
        "name": "Batería SOC",
        "unit": PERCENTAGE,
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_power": {
        "key": "Measurement.Bat.P",
        "name": "Batería Potencia",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_voltage": {
        "key": "Measurement.Bat.V",
        "name": "Batería Voltaje",
        "unit": UnitOfElectricPotential.VOLT,
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_current": {
        "key": "Measurement.Bat.A",
        "name": "Batería Corriente",
        "unit": UnitOfElectricCurrent.AMPERE,
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_temperature": {
        "key": "Measurement.Bat.Temp",
        "name": "Batería Temperatura",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "grid_power": {
        "key": "Measurement.Grid.P",
        "name": "Red Potencia",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
     "grid_frequency": {
        "key": "Measurement.Grid.F",
        "name": "Red Frecuencia",
        "unit": UnitOfFrequency.HERTZ,
        "device_class": SensorDeviceClass.FREQUENCY,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "pv_power": {
        "key": "Measurement.Pv.P",
        "name": "PV Potencia",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "load_power": {
        "key": "Measurement.Consumption.P",
        "name": "Consumo Potencia",
        "unit": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # Sensores de fase (ejemplo)
    "grid_voltage_l1": {
        "key": "Measurement.Grid.V.L1",
        "name": "Red Voltaje L1",
        "unit": UnitOfElectricPotential.VOLT,
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "grid_voltage_l2": {
        "key": "Measurement.Grid.V.L2",
        "name": "Red Voltaje L2",
        "unit": UnitOfElectricPotential.VOLT,
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "grid_voltage_l3": {
        "key": "Measurement.Grid.V.L3",
        "name": "Red Voltaje L3",
        "unit": UnitOfElectricPotential.VOLT,
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Configura los sensores desde la config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    sensors = []
    for id_suffix, config in SENSOR_MAP.items():
        # Solo añade el sensor si la clave existe en el primer refresh
        if config["key"] in coordinator.data:
            sensors.append(
                SpockSmaSensor(
                    coordinator=coordinator,
                    entry_id=entry.entry_id,
                    id_suffix=id_suffix,
                    config=config,
                )
            )
        else:
            _LOGGER.debug(f"Sensor '{id_suffix}' (clave {config['key']}) no encontrado en datos de SMA, se omitirá.")
    
    async_add_entities(sensors)

class SpockSmaSensor(CoordinatorEntity, SensorEntity):
    """Sensor que lee datos del Coordinador de telemetría SMA."""

    def __init__(self, coordinator, entry_id, id_suffix, config):
        super().__init__(coordinator)
        self._data_key = config["key"]
        
        # Atributos de la entidad
        self._attr_name = config["name"]
        self._attr_native_unit_of_measurement = config.get("unit")
        self._attr_device_class = config.get("device_class")
        self._attr_state_class = config.get("state_class")
        self._attr_unique_id = f"{entry_id}_{id_suffix}"
        
        # (Opcional) Enlazar entidad a un dispositivo (no implementado aquí)
        # self._attr_device_info = ... 

    @property
    def native_value(self):
        """Retorna el valor del sensor desde el coordinador."""
        if self.coordinator.data:
            return self.coordinator.data.get(self._data_key)
        return None
