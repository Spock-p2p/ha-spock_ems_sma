from datetime import timedelta

DOMAIN = "spock_ems_sma"

# --- Configuración de Polling (Telemetría SMA) ---
# Intervalo fijo para leer datos del SMA Data Manager
SCAN_INTERVAL_SMA = timedelta(seconds=10)

# --- Configuración de la API de Spock (PUSH/PULL) ---

# 1. Endpoint REMOTO (Outbound)
#    URL en la nube de Spock donde ENVIAMOS la telemetría
SPOCK_TELEMETRY_API_ENDPOINT = "https://ems-ha.spock.es/api/ems_sma" 

# 2. Path LOCAL (Inbound)
#    Path local que registramos en HA para RECIBIR comandos
SPOCK_COMMAND_API_PATH = "/api/spock_ems_sma"

# Claves para el config_flow y el data entry
CONF_SPOCK_API_TOKEN = "spock_api_token"
CONF_PLANT_ID = "plant_id"

# --- Constantes de SMA ---
# Plataformas a cargar
PLATFORMS = ["sensor"]

# Grupo de usuario recomendado para SMA ennexOS
SMA_DEFAULT_USERNAME = "installer"
