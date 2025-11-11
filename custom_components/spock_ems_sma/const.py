from datetime import timedelta

DOMAIN = "spock_ems_sma"

# --- Configuración de Polling (Telemetría SMA) ---
SCAN_INTERVAL_SMA = timedelta(seconds=30)

# --- Configuración de la API de Spock (PUSH/PULL) ---
SPOCK_TELEMETRY_API_ENDPOINT = "https://ems-ha.spock.es/api/ems_marstek" 
SPOCK_COMMAND_API_PATH = "/api/spock_ems_sma"

# Claves de configuración
CONF_SPOCK_API_TOKEN = "spock_api_token"
CONF_PLANT_ID = "plant_id"
CONF_GROUP = "group"
GROUPS = ["user", "installer"]
DEFAULT_GROUP = "installer"

# --- CONSTANTES DEL SWITCH MAESTRO ---
MASTER_SWITCH_NAME = "Spock EMS SMA Control"
MASTER_SWITCH_KEY = "master_control"

# Plataformas a cargar
PLATFORMS = ["sensor", "switch"]
