"""Constants for the Spock EMS SMA integration."""

DOMAIN = "ha_spock_ems_sma"

# Config Keys
CONF_SMA_IP = "sma_ip"
CONF_SMA_PORT = "sma_port"
CONF_SMA_UNIT_ID = "sma_unit_id"

# Defaults
DEFAULT_SMA_PORT = 502
DEFAULT_SMA_UNIT_ID = 3

# SMA Modbus Registers
# 40149: Active Power Setpoint (Signed 32-bit) - Negativo=Carga, Positivo=Descarga
SMA_REG_SETPOINT = 40149 
# 40151: Control Mode (Unsigned 32-bit) - 802=Manual, 803=Auto
SMA_REG_CONTROL_MODE = 40151

# SMA Control Values
SMA_MODE_MANUAL = 802
SMA_MODE_AUTO = 803
