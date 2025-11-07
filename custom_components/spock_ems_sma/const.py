from datetime import timedelta

DOMAIN = "spock_ems_sma"

# --- Configuración de Polling (Telemetría SMA) ---
SCAN_INTERVAL_SMA = timedelta(seconds=10)

# --- Configuración de la API de Spock (PUSH/PULL) ---
# 1. Endpoint REMOTO (Outbound) - URL de tu API
SPOCK_TELEMETRY_API_ENDPOINT = "https://ems-ha.spock.es/api/ems_marstek" 

# 2. Path LOCAL (Inbound) - Path para recibir comandos
SPOCK_COMMAND_API_PATH = "/api/spock_ems_sma"

# Claves para el config_flow y el data entry
CONF_SPOCK_API_TOKEN = "spock_api_token"
CONF_PLANT_ID = "plant_id"
CONF_GROUP = "group"
GROUPS = ["user", "installer"]
DEFAULT_GROUP = "installer"

# Plataformas a cargar
PLATFORMS = ["sensor"]
