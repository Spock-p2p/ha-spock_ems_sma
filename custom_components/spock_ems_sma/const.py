"""Constantes de la integración Spock EMS SMA."""

from datetime import timedelta

DOMAIN = "spock_ems_sma"

# ---------------------------------------
# Configuración de Spock API
# ---------------------------------------
API_ENDPOINT = "https://api.spock.energy/v1/ems/push"
CONF_API_TOKEN = "api_token"
CONF_PLANT_ID = "plant_id"

# ---------------------------------------
# Parámetros PV existentes (lectura)
# ---------------------------------------
CONF_PV_IP = "pv_ip"
CONF_PV_PORT = "pv_port"
CONF_PV_SLAVE = "pv_slave"

# ---------------------------------------
# NUEVOS — Parámetros Modbus (control batería)
# ---------------------------------------
CONF_MODBUS_PORT = "modbus_port"         # default: 502
CONF_MODBUS_UNIT_ID = "modbus_unit_id"   # default: 3

# ---------------------------------------
# Intervalo de Polling (lectura telemetría SMA)
# ---------------------------------------
SCAN_INTERVAL_SMA = timedelta(seconds=30)
