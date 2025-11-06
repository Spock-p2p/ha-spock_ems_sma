"""Constantes para la integración Spock EMS SMA."""

DOMAIN = "spock_ems_sma"

# --- API de Spock ---
API_ENDPOINT = "https://flex.spock.es/api/ems_marstek"

# --- Constantes de Configuración ---
CONF_API_TOKEN = "api_token"
CONF_PLANT_ID = "plant_id"

# IPs de los dispositivos Modbus (Lectura)
CONF_BATTERY_IP = "battery_ip" 
CONF_BATTERY_PORT = "battery_port"
CONF_BATTERY_SLAVE = "battery_slave"
CONF_PV_IP = "pv_ip" 
CONF_PV_PORT = "pv_port"
CONF_PV_SLAVE = "pv_slave"

# Configuración Speedwire (Escritura)
CONF_SHM_IP = "shm_ip" # IP del Sunny Home Manager 2.0
CONF_SHM_GROUP = "shm_group" # "user" o "installer"
CONF_SHM_PASSWORD = "shm_password"


# --- Plataformas ---
PLATFORMS: list[str] = ["switch"]

# --- Defaults ---
DEFAULT_MODBUS_PORT = 502
DEFAULT_MODBUS_SLAVE = 3 
DEFAULT_SCAN_INTERVAL_S = 30
DEFAULT_SHM_GROUP = "user"

# --- Registros Modbus SMA ---
SMA_REG_BAT_POWER = 30843      
SMA_REG_BAT_SOC = 30845        
SMA_REG_BAT_CAPACITY = 30849   
SMA_REG_GRID_POWER = 30867     
SMA_REG_PV_POWER = 30775
