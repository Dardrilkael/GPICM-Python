import paho.mqtt.client as mqtt
import json

import random
import time
from datetime import date, timedelta

class EstacaoController:
    def __init__(self, estacao):
        self.estacao = estacao
        self.broker = "broker.gpicm-ufrj.tec.br"
        self.port = 1883
        self.username = "telemetria"
        self.password = "kancvx8thz9FCN5jyq"
        self.client = mqtt.Client()
        self.connected = False
        self.output_sys_report = []

        # Bind eventos
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

        # Configura autenticação
        self.client.username_pw_set(self.username, self.password)

    def connect(self):
        try:
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
        except Exception as e:
            print("Erro ao conectar:", e)
            self.output_sys_report.append(f"Erro ao conectar: {e}")

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("Conectado ao broker com sucesso.")
            self.connected = True
        else:
            print(f"Falha na conexão. Código de retorno: {rc}")
            self.output_sys_report.append(f"Erro na conexão: Código {rc}")

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        print("Desconectado do broker.")

    def publish_message(self, command):
        topic = f"sys/prefeituras/macae/estacoes/{self.estacao}"
        payload = json.dumps(command)
        self.client.publish(topic, payload)
        print(f"[MQTT] Publicado para {topic} -> {payload}")

    def execute_command(self, command):
        print("Executando comando:", command)
        if self.connected:
            self.publish_message(command)
            self.output_sys_report.append(f"Comando enviado: {command}")
        else:
            self.output_sys_report.append("Conecte-se ao broker primeiro.")
            print("Não conectado ao broker.")

    def create_file_command(self, filename, content):
        command = {
            "cmd": "a",
            "fn": filename,
            "content": content
        }
        self.execute_command(command)


if __name__ == "__main__":
    estacao = "est223"
    controller = EstacaoController(estacao)
    controller.connect()

    import time
    time.sleep(2)  # Espera conexão

    start_date = date(2016, 7, 1)
    num_files = 10  # how many files to generate

    for i in range(num_files):
        current_date = start_date + timedelta(days=i)
        date_str = current_date.strftime("%#d-%#m-%Y")  # Works on Windows
        filename = f"/falhas/{date_str}.txt"

        # CSV header
        header = "timestamp,temperatura,umidade_ar,velocidade_vento,rajada_vento,dir_vento,volume_chuva,pressao,uid,identidade"

        # Generate some rows
        rows = []
        for _ in range(random.randint(3,4)):
            timestamp = int(time.time()) + random.randint(-100000, 100000)
            temperatura = f"{random.uniform(18, 35):.2f}"         # Normal daily temperature range
            umidade_ar = f"{random.uniform(40, 90):.2f}"  
            velocidade_vento = f"{random.uniform(0, 10):.2f}"
            rajada_vento = f"{random.uniform(0, 15):.2f}"
            dir_vento = random.randint(0, 360)
            volume_chuva = f"{random.uniform(0, 20):.2f}"
            pressao = f"{random.uniform(980, 1030):.2f}"
            uid = random.randint(100, 999)
            identidade = f"est{uid}"
            row = f"{timestamp},{temperatura},{umidade_ar},{velocidade_vento},{rajada_vento},{dir_vento},{volume_chuva},{pressao},{uid},{identidade}"
            rows.append(row)

        content = header + "\n" + "\n".join(rows)
        time.sleep(2)  # Simulate some delay between file creations
        controller.create_file_command(filename, content)

    print("Files created with updated CSV format.")




    #controller.create_file_command("/falhas/14-5-2025.txt", random csv data)
