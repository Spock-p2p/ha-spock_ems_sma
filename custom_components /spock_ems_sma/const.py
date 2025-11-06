"""Constantes para la integración Spock EMS Modbus."""

DOMAIN = "spock_ems_modbus"

# --- API de Spock ---
API_ENDPOINT = "https://flex.spock.es/api/ems_marstek"

# --- Constantes de Configuración ---
CONF_API_TOKEN = "api_token"
CONF_PLANT_ID = "plant_id"
CONF_MODBUS_IP = "modbus_ip"
CONF_MODBUS_PORT = "modbus_port"
CONF_MODBUS_SLAVE = "modbus_slave"

# --- Plataformas ---
PLATFORMS: list[str] = ["switch"]

# --- Defaults ---
DEFAULT_MODBUS_PORT = 502
DEFAULT_MODBUS_SLAVE = 1
DEFAULT_SCAN_INTERVAL_S = 30
