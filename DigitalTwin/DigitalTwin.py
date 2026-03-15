#!/home/admin/digitaltwin/venv/bin/python
import paho.mqtt.client as mqtt
import json
import time
import threading
import schedule
import sys
import os

class PillCommands:
    # Comandi verso le schede
    MONDAY_CHECK = "REQ_MON"
    TUESDAY_CHECK = "REQ_TUE"
    WEDNESDAY_CHECK = "REQ_WED"
    THURSDAY_CHECK = "REQ_THU"
    FRIDAY_CHECK = "REQ_FRI"
    SATURDAY_CHECK = "REQ_SAT"
    SUNDAY_CHECK = "REQ_SUN"
    DAILY_CHECK = "REQ"
    ALARM_ON = "ALM_ON"
    ALARM_OFF = "ALM_OFF"
    SYNC = "SYNC_REQ"

    # Metodo per ottenere la stringa formattata
    @staticmethod
    def get(command_name):
        return getattr(PillCommands, command_name.upper(), "UNKNOWN")

    @staticmethod
    def get_command_by_day(day):
        day = day.lower()
        if day == "monday":
            return PillCommands.MONDAY_CHECK
        elif day == "tuesday":
            return PillCommands.TUESDAY_CHECK
        elif day == "wednesday":
            return PillCommands.WEDNESDAY_CHECK
        elif day == "thursday":
            return PillCommands.THURSDAY_CHECK
        elif day == "friday":
            return PillCommands.FRIDAY_CHECK
        elif day == "saturday":
            return PillCommands.SATURDAY_CHECK
        elif day == "sunday":
            return PillCommands.SUNDAY_CHECK
        else:
            return "UNKNOWN"

    @staticmethod
    def get_day_code(day):
        day = day.lower()
        if day == "monday":
            return 0
        elif day == "tuesday":
            return 1
        elif day == "wednesday":
            return 2
        elif day == "thursday":
            return 3
        elif day == "friday":
            return 4
        elif day == "saturday":
            return 5
        elif day == "sunday":
            return 6
        else:
            return -1

class PillBoxDigitalTwin:
    def __init__(self, username, key, broker="io.adafruit.com", port=1883):
        self.username = username
        self.key = key
        self.broker = broker
        self.port = port

        self.week = {
            "monday" : False,
            "tuesday" : False,
            "wednesday" : False,
            "thursday" : False,
            "friday" : False,
            "saturday" : False,
            "sunday" : False,

        }

        # Stato interno del Twin (Modulare e serializzabile)
        self.state = {
            "pill_taken": False,
            "last_update": None,
            "device_source": None,
            "week_status": self.week,
            "day_of_week": None,
            "hour_check": None
        }

        # Configurazione Client MQTT
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(self.username, self.key)

        # Assegnazione dei metodi di callback
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"[*] Connesso al Broker Adafruit come: {self.username}")
            # Iscrizione ai feed (Topic)
            # Usiamo un formato modulare per i nomi dei feed
            client.subscribe(f"{self.username}/feeds/digital-twin-core")
            # client.subscribe(f"{self.username}/feeds/pill-status")
        else:
            print(f"[!] Errore di connessione, codice: {reason_code}")

    def on_message(self, client, userdata, msg):
        """Gestisce i messaggi in entrata e aggiorna lo stato del Twin"""
        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic
            print(f"[<-] Ricevuto su {topic}: {payload}")

            # Logica di aggiornamento dello stato
            if "action" in payload and payload["action"] == "confirm_intake":
                self.update_twin_state(True, payload.get("device"))

            if "action" in payload and payload["action"] == "connection":
                print(f'dispositivo {msg.device} connesso')#da implementare sulla scheda

        except Exception as e:
            print(f"[!] Errore nel parsing del messaggio: {e}")

    def update_twin_state(self, status, device):
        """Metodo modulare per cambiare lo stato e notificare il sistema"""
        self.state["pill_taken"] = status
        self.state["last_update"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.state["device_source"] = device

        print(f"[#] Stato Twin aggiornato: {self.state}")

        # Notifica il nuovo stato a tutti i dispositivi (Broadcast)
        # self.publish_state()

    def publish_state(self):
        """Invia lo stato attuale sul feed del Digital Twin"""
        topic = f"{self.username}/feeds/digital-twin-core"
        self.client.publish(topic, json.dumps(self.state), retain=True)
        print(f"[->] Stato pubblicato su {topic}")

    def send_command(self, target_device, command_type, value):
        """
        Invia un comando specifico a una scheda.
        :param target_device: ID della scheda (es. 'casa' o 'ufficio' o 'all')
        :param command_type: Il tipo di comando (es. 'set_led', 'buzzer')
        :param value: Il valore del comando (es. 'GREEN', 'OFF', 'ON')
        """
        payload = {
            "target": target_device,
            "command": command_type,
            "val": value,
            "sender": "digital_twin_engine",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

        # Topic dove le schede sono in ascolto
        topic = f"{self.username}/feeds/pill-commands"

        self.client.publish(topic, json.dumps(payload))
        print(f"[->] Comando inviato a {target_device}: {command_type} -> {value}")

    def run_scheduler_loop(self): # Rinominata per chiarezza
        """Il loop dello scheduler eseguito nel thread"""
        # Cambia l'orario qui per i tuoi test
        self.hour_check = "12:48"
        schedule.every().day.at(self.hour_check).do(self.trigger_global_check)

        # Consiglio: aggiungi un controllo ogni minuto per vedere se il thread è vivo
        # schedule.every(1).minutes.do(lambda: print("[Twin] Scheduler in esecuzione..."))

        while True:
            schedule.run_pending()
            time.sleep(1)

    def trigger_global_check(self):
        """Il cervello interroga attivamente le schede"""
        print("[!] Ore 10:00 - Avvio controllo globale assunzione...")
        self.day_of_week = time.strftime("%A").lower()

        # Invia il comando di controllo a tutte le schede tramite Node-RED
        self.send_command(target_device="all", command_type=PillCommands.DAILY_CHECK, value=PillCommands.get_day_code(self.day_of_week))

        # Avvia un timer di cortesia: se tra 10 min è ancora False, invia allarme
        threading.Timer(600, self.check_if_missed).start()

    def check_if_missed(self):
        if not self.state["pill_taken"]:
            print("[!!!] ATTENZIONE: Pillola non rilevata. Invio allarmi.")
            self.send_command(target_device="all", command_type="alarm", value="ON")

    def start(self):
        # Avvia lo scheduler in un thread dedicato
        daemon_sched = threading.Thread(target=self.run_scheduler_loop, daemon=True)
        daemon_sched.start()
        self.day_of_week = time.strftime("%A").lower()
        print(f"[*] Thread Scheduler avviato. Ora sistema: {time.strftime('%H:%M:%S')}, Giorno: {self.day_of_week}")

        """Avvia il loop di comunicazione"""
        self.client.connect(self.broker, self.port)
        self.client.loop_forever()

def main():
    try:
        ADAFRUIT_USER = os.environ.get("ADA_USERNAME")
        ADAFRUIT_KEY = os.environ.get("ADA_KEY")
        sys.stdout = open("/home/admin/digitaltwin/twin.log", "a", buffering=1)  # line-buffered
        sys.stderr = open("/home/admin/digitaltwin/twin.err", "a", buffering=1)
        twin = PillBoxDigitalTwin(ADAFRUIT_USER, ADAFRUIT_KEY)
        twin.start()
    except KeyboardInterrupt:
        print("Arresto del digital twin...")

if __name__ == "__main__":
    main()
