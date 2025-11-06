{
    "config": {
        "step": {
            "user": {
                "title": "Configuración de Spock EMS (Modbus)",
                "description": "Introduce los detalles de tu API de Spock y la conexión Modbus TCP de tu inversor.",
                "data": {
                    "api_token": "Spock EMS API Token",
                    "plant_id": "Spock EMS ID de Planta",
                    "modbus_ip": "Dirección IP del Inversor (Modbus)",
                    "modbus_port": "Puerto Modbus TCP",
                    "modbus_slave": "ID de Esclavo (Slave ID) Modbus"
                }
            }
        },
        "abort": {
            "already_configured": "Esta combinación de IP e ID de Planta ya está configurada."
        }
    },
    "options": {
        "step": {
            "init": {
                "title": "Opciones de Spock EMS (Modbus)",
                "data": {
                    "api_token": "Spock EMS API Token",
                    "plant_id": "Spock EMS ID de Planta",
                    "modbus_ip": "Dirección IP del Inversor (Modbus)",
                    "modbus_port": "Puerto Modbus TCP",
                    "modbus_slave": "ID de Esclavo (Slave ID) Modbus"
                }
            }
        }
    },
    "entity": {
        "switch": {
            "polling_enabled": {
                "name": "Habilitar Sondeo Modbus/API"
            }
        }
    }
}
