import sys
import json
import threading
import base64
import os
import csv  # Importar o módulo csv para manipulação de arquivos CSV
import re
from datetime import datetime, timezone
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QMessageBox, QGroupBox, QFormLayout, QComboBox, QFileDialog
)
from PyQt6.QtCore import pyqtSignal, QObject, QTimer,QSize
import paho.mqtt.client as mqtt
from numpy.ma.core import empty
from PyQt6.QtCore import Qt 
import requests
from urllib.parse import urljoin

# Replace with the repository you want (format: owner/repo)
repo = "Dardrilkael/Arduino-Weather-Station"
url = f"https://api.github.com/repos/{repo}/releases"

headers = {
    "Accept": "application/vnd.github+json",
    # "Authorization": "Bearer YOUR_GITHUB_TOKEN",  # optional
}


import requests
from requests.exceptions import RequestException

def fetch_files(url):
    try:
        # Attempt to fetch the data from the URL
        response = requests.get(url)

        # Check if the request was successful
        if response.status_code == 200:
            file_data = response.json()

            # Prepare lists with default "Escolha" as the first option
            file_names = ["Escolha"] + [file['name'] for file in file_data]
            http_base_url = url.replace("https://", "http://")
            download_links = [""] + [urljoin(http_base_url, "/admin"+file['url']) for file in file_data]
            #download_links = [""] + [urljoin(url, "file['url']") for file in file_data]
            descriptions = [""] + [file.get('description', '') for file in file_data]
            versions = [""] + [file.get('version', '') for file in file_data]  # Extract version
            upload_dates = [""] + [file.get('uploadDate', '') for file in file_data]  # Extract uploadDate
            
            return {
                "file_names": file_names,
                "download_links": download_links,
                "descriptions": descriptions,
                "versions": versions,
                "upload_dates": upload_dates
            }

        else:
            print(f"Failed to retrieve data. Status code: {response.status_code}")
            return {
                "file_names": ["Escolha"],
                "download_links": [""],
                "descriptions": [""],
                "versions": [""],
                "upload_dates": [""]
            }

    except RequestException as e:
        # Catch any network-related or server-related issues
        print(f"A network error occurred: {e}")
        return {
            "file_names": ["Escolha"],
            "download_links": [""],
            "descriptions": [""],
            "versions": [""],
            "upload_dates": [""]
        }
    except Exception as e:
        # Catch any other unforeseen exceptions
        print(f"An unexpected error occurred: {e}")
        return {
            "file_names": ["Escolha"],
            "download_links": [""],
            "descriptions": [""],
            "versions": [""],
            "upload_dates": [""]
        }



def timestamp_to_datetime(timestamp):
    if not str.isdigit(str(timestamp)): return timestamp
    ts = int(timestamp)
    # Convert timestamp to a timezone-aware datetime object (UTC)
    dt_object = datetime.fromtimestamp(ts-3*60*60, tz=timezone.utc)
    
    # Format the datetime object with newlines for separate lines
    formatted_date = dt_object.strftime('%d/%m/%Y\n%H:%M')

    return formatted_date

def make_counter():
    count = 0  

    def counter():
        nonlocal count 
        count += 1
        if(count>900):count=0
        return count

    return counter

my_counter = make_counter()

# Configurações do broker e credenciais
broker = "broker.gpicm-ufrj.tec.br"
port = 1883
username = "telemetria"
password = "kancvx8thz9FCN5jyq"

# Mensagens JSON para comandos MQTT
'''msg_update = {
    "cmd": "update",
    "url": "http://update.gpicm-ufrj.tec.br:18000/uploads/versao11.bin",
    "id": "3"
}'''
msg_reset = {"cmd": "r"}
def messagelist(dir):
    # Create the message list dynamically based on the given directory
    msg_list = {
        "cmd": "l",
        "dir": dir
    }
    return msg_list
# Classe para sinais MQTT e interação com UI
class MqttClient(QObject):
    message_signal = pyqtSignal(str, str)  # Sinal para UI exibir mensagens (tópico, payload)

    def __init__(self, estacao):
        super().__init__()
        self.estacao = estacao
        self.client = mqtt.Client()
        self.client.username_pw_set(username, password)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.connected = False
        self.mqtt_thread = None
        self.files_falhas = {}
        self.files_metricas = {}
        self.Files = self.files_falhas 
        self.filesID = ""
        # Tópicos configurados dinamicamente com base na estação
        self.publish_sys = f"sys/prefeituras/macae/estacoes/{self.estacao}"
        self.response_ota = f"sys-report/prefeituras/macae/estacoes/{self.estacao}/OTA"
        self.response_handshake  = f"sys-report/prefeituras/macae/estacoes/{self.estacao}/handshake"
        self.response_healthcheck  = f"sys-report/prefeituras/macae/estacoes/{self.estacao}/healthcheck"
        self.response_sys_report = f"sys-report/prefeituras/macae/estacoes/{self.estacao}"
        self.publish_json = f"batch/prefeituras/macae/estacoes/{self.estacao}"
        self.response_json = f"file/prefeituras/macae/estacoes/{self.estacao}"
        self.publish_json_rec = f"/prefeituras/macae/estacoes/{self.estacao}"
        self.dns = f"/dns/ota"
    def connect(self):
        if not self.connected:
            self.client.connect(broker, port, keepalive=60)
            self.connected = True
            self.mqtt_thread = threading.Thread(target=self.client.loop_forever)
            self.mqtt_thread.start()

    def disconnect(self):
        if self.connected:
            self.client.disconnect()
            self.connected = False
            if self.mqtt_thread is not None:
                self.mqtt_thread.join()
                self.mqtt_thread = None

    def on_connect(self, client, userdata, flags, rc):
        print("Conectado ao broker com código de retorno:", rc)
        # Inscreve-se nos tópicos de resposta
        self.client.subscribe(self.response_ota)
        self.client.subscribe(self.response_sys_report)
        self.client.subscribe(self.response_json)  # Inscreve-se no tópico de file
        self.client.subscribe(self.response_handshake)
        self.client.subscribe(self.response_healthcheck)
        self.client.subscribe(self.publish_json_rec)
        self.client.subscribe(self.dns)
        print(f"Inscrito nos tópicos: \n\t{self.response_ota},\n\t{self.response_sys_report},\n\t{self.response_json},\n\t{self.response_handshake},\n\t{self.response_healthcheck},\n\t{self.publish_json_rec}")

    def publish_message(self, msg):
        if self.connected:
            self.client.publish(self.publish_sys, json.dumps(msg))
    def publish_delete(self, file):
        if self.connected:
            self.client.publish(self.publish_sys, )

    def on_message(self, client, userdata, msg):
        # Emitir mensagem recebida via sinal para a interface gráfica
        payload = msg.payload.decode()
        print(f"Mensagem recebida no tópico {msg.topic}: {payload}")  # Debugging
        if msg.topic == self.response_json:
            payload = self.on_file_message(payload);
        self.message_signal.emit(msg.topic, payload)

    def on_file_message(self, msg):
        try:
            json_data = json.loads(msg)

            if 'data' in json_data:
                base64_data = json_data['data']
                filename = json_data.get('filename', 'unknown_file/file.txt')
                if "/metricas" in filename: self.Files = self.files_metricas
                else: self.Files = self.files_falhas
                ff = os.path.basename(filename)
                _id = json_data.get('id', '0')
                if base64_data == 'complete':
                    print("transferencia de arquivo completa para", filename)
                    return  "transferencia de arquivo completa"

                decoded_data = base64.b64decode(base64_data)
                
                udata = decoded_data#.decode('utf-8')

                if (ff in self.Files) and (self.filesID != _id):
                    print(f"Clearing files dictionary {self.filesID} and {_id}")
                    self.Files.clear()
                    
                    
                if ff not in self.Files:
                    self.Files[ff] = b""
                    self.filesID = _id
                self.Files[ff]+=udata;
                print("---------------------------------------------------------------------------------------")
                print(list(self.Files.keys()))
                print("---------------------------------------------------------------------------------------")
                return udata.decode('utf-8')
            else:
                print("Received message without 'data' key.")
        except json.JSONDecodeError:
            print("Failed to decode JSON message.")
        except base64.binascii.Error as e:
            print(f"Base64 decode error: {e}")
        except Exception as e:
            print(f"Error processing message: {e}")


    def csv_to_json(self, csv_file_path):
        # Lista para armazenar os dados
        data = []
        
        # Lendo o arquivo CSV
        fieldnames = ("timestamp", "temperatura", "umidade_ar", "velocidade_vento", "rajada_vento", "dir_vento", "volume_chuva", "pressao", "uid", "identidade")
        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file, fieldnames)  # Usa DictReader para tratar cada linha como um dicionário
            for row in csv_reader:
                    try:
                        # Convert fields that should be numbers
                        row["timestamp"] = int(row["timestamp"]) if row["timestamp"] else None  # Convert to integer
                        row["temperatura"] = float(row["temperatura"]) if row["temperatura"] else None
                        row["umidade_ar"] = float(row["umidade_ar"]) if row["umidade_ar"] else None
                        row["velocidade_vento"] = float(row["velocidade_vento"]) if row["velocidade_vento"] else None
                        row["rajada_vento"] = float(row["rajada_vento"]) if row["rajada_vento"] else None
                        row["dir_vento"] = int(row["dir_vento"]) if row["dir_vento"] else None  # Convert to integer
                        row["volume_chuva"] = float(row["volume_chuva"]) if row["volume_chuva"] else None
                        row["pressao"] = float(row["pressao"]) if row["pressao"] else None
                        converted_row = json.dumps(row)
                        print(converted_row)  # aqui é só enviar para o tópico /prefeituras/macae/estacoes/xxxx
                        self.client.publish(self.publish_json_rec, str(converted_row))
                    except ValueError as e:
                        print(f"Skipping row due to error: {e}")
                        continue  

    # Leave 'uid' and 'identidade' as strings
# Classe da Interface Gráfica
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gerenciador de Estações MQTT")
        self.setGeometry(100, 100, 800, 600)  # Aumentando a altura para acomodar mais caixas
        self.version = "0.0.0"
        self.status_value=3
        #icon = QIcon("nuvem.png")  # Substitua pelo caminho do seu ícone
        #self.setWindowIcon(icon)
        # Centraliza a janela na tela
        screen = QApplication.primaryScreen()
        screen_rect = screen.availableGeometry()
        x = (screen_rect.width() - self.width()) // 2
        y = (screen_rect.height() - self.height()) // 2
        self.move(x, y-100)

        self.commandQueue = []
        self.waiting = False

        self.timer = QTimer()
        self.timer.timeout.connect(self.execute_next)
        self.timer.start(100)
        # Variável para armazenar dados recebidos do tópico batch
        #self.received_batch_data = []
        setCurrentCommand = {}
        # Layout principal
        main_layout = QVBoxLayout()
        self.shouldClearCombo= [0,0]
        self.d_values =[]
        # Seção de Conexão
        connection_group = QGroupBox("Conexão com Estação")
        connection_layout = QFormLayout()

        self.estacao_input = QLineEdit()
        self.estacao_input.setPlaceholderText("Digite apenas o número da estação neste campo...")
        connection_layout.addRow("Número da Estação:", self.estacao_input)
        self.conection_label = QLabel('desconectado')
        #connection_layout.addRow(self.conection_label)
        #self.version_label = QLabel('Versao: unkown', self)
        self.url = ""

        button_layout = QHBoxLayout()

        self.connect_button = QPushButton("Conectar")
        self.connect_button.setToolTip("Clique neste botão para se conectar a uma estação.")
        self.connect_button.setStyleSheet(style())
        #icon_connect = QIcon("entrar.png")
        #self.connect_button.setIcon(icon_connect)
        self.connect_button.clicked.connect(self.connect_mqtt)
        button_layout.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("Desconectar")
        self.disconnect_button.setToolTip("Clique neste botão para se desconectar da estação.")
        self.disconnect_button.setStyleSheet(
            style2())
        #icon_close = QIcon("sair.png")
        #self.disconnect_button.setIcon(icon_close)
        self.disconnect_button.clicked.connect(self.disconnect_mqtt)
        self.disconnect_button.setEnabled(False)
        button_layout.addWidget(self.disconnect_button)

        connection_layout.addRow(button_layout)
        connection_group.setLayout(connection_layout)
        main_layout.addWidget(connection_group)

        # Seção de Comandos
        commands_group = QGroupBox("Comandos enviados para estação")
        commands_group_update = QGroupBox("Comandos de Atualização")

        main_commands_layout = QVBoxLayout()
        commands_layout = QHBoxLayout()
        #button_size = (120, 40)
        
        #Get version
        self.version_button = QPushButton("Obter Versao")
        self.version_button.setToolTip("Clique neste botão para se obter a versão do Firmware da estação.")
        self.version_button.setStyleSheet(style())
        self.version_button.clicked.connect(lambda: self.send_command({"cmd": "v"}))  # Alterado para o novo método
        commands_layout.addWidget(self.version_button)
        self.version_label = QLabel('Versao: unkown', self)
        commands_layout.addWidget(self.version_label)
        
        line_break = QLabel('')
        commands_layout.addWidget(line_break)

        update_commands_layout = QVBoxLayout()
        update_commands_layout_one = QHBoxLayout()
        update_commands_layout_two = QHBoxLayout()
        # Input fields for update command parameters
        self.update_url_input = QLineEdit()
        self.update_url_input.setPlaceholderText("Cole aqui o nome do binário para atualização")
        update_commands_layout_one.addWidget(self.update_url_input)  # Add the URL input to the layout

        self.fetch_combo = QComboBox()
        #return {"file_names": [], "download_links": [], "descriptions": []}
        self.fetch_combo.setStyleSheet(style_combo())
        self.fetch_combo.setToolTip("Clique neste botão para obter a versão do binário.")
        self.fetch_combo.currentIndexChanged.connect(lambda index: {self.update_url_input.setText(self.query["download_links"][index]), self.description_label.setText('Descrição: ' + self.query["descriptions"][index])})
        update_commands_layout_one.addWidget(self.fetch_combo)
        icon_base64 = '''
            iVBORw0KGgoAAAANSUhEUgAAADIAAAAyCAYAAAAeP4ixAAAACXBIWXMAAAsTAAALEwEAmpwYAAAFM0lEQVR4nO2aa4hVVRTHfzenO9HE6EzeGQsq7fGht1YYRQSZElk61gT2sKIoUKmsoCcREQP6qS/Vh5AsIwatiFCIIMae9nKsEUenMc2yp5ZZUDOaOScW/Desztx755zrvXO94R8Oc/c+Z6+91l6PvfbaA4fx/8VRwBXAYmAl0A3sAn4HfgN2AD3ACuBx4DIgyyGCI4B2YBXwFxClfP6UYDNEqyqrPx/4yjF1APgM6ABuAC4EWoGxQBNwAjAFuBFYom8PuPFfAnNHU6CLgT7HwBZgAdBSAq0csChGbz1wbsKxJWvhKbeKG4FrYit4EnAbsBR4F9gmP/kZ6AfeA54FbgeOd+MywBxpxWj/DTxWRDum6d5ShDDpP3KTPOkcNSvG1qb0jyHRnOdo1QEPAfv0zetAQ4yXCU6DqTAJ2KqB22XnYRVt9b93zFmEehW4G5gGnAqMl9nZ7+nA/cDqWHD4Tr6TEe3zpc1IvjTWaWKTG5cYLfKBQNAIGU6UmQSC3XJwM7+ksJW+M8bYGmdytvKfq/9DYKLMyWs1EYypdc4BG9Vv8X+3+nco/B4MxgB3AL+K5k7gUr1r1CJFztw2pxXkaX281UWkNmCv+l8DxlE+mCa6RHsAuFL9xwHfqL9XVpFYkJlyxn2yV8PlToglzp7LiSOBFzSHzXWJ+s8GPnEhN5EgWecXD6hvotKMSClIJZEBXnRmZiGdWChOJMh9zhbrRCCE3pUV0kQ+MxvQnJ153o8oiKn2B310tfoWuNAbHL6SaHXRaWOBHXxEQa53TmUrf7TUa32zqDwmuHC82YX71IK8rQ8sIUQbW4jjlYYx7UNrkicvGhWl9gPN6tugARZ2K4lcns0uKlWQa/XyfbXPdJHDfKdmsFiMP6H2IrUtrtcUVovxkHKsUPtWagz9Yvx0tXvUvoDq44wCPmI8D8MuvQx5VUjiLA2vNpoLCGLZxjCEPKpe7ZBtHgqVjjrx8pPLzENGPAyB8XCm2F8Dggzm+zgkhfHnWKqPJvFiZ/qQAUSqBRR09vhzGtXHZPFiBQ3DWS6NqSnME+PPqD1X7TeoMTwX29M61La/NYMxwI86sdqxF3c+ml1oUNqkrfdgKn4JMTOWgedUJBzMU/MqSZBi54Vyokvz3RI7WrxZbFCx9LjFpdp9sZJnpTBd832r/SzjqoztpQiS07EzmNNoaKLBFUGCNtpcZdI2ydSCvKz+gVHShGGZ5uySJrJur7uHERAXJJRgTnHVxWWjUEl5VHP9onsV39eX5KDnBcmpKGbFMXSrFPKvpSOptgxC7FV51jBVtwBD4oOkgviSzHaX2re75PKtMvuKVWyWOyHaXF71tfrtfiYRfGgNaXIkzYTSvtVk97ik7aYymNoMd423R1cSaM4ex0N9WkFCdJrkdtF1LhM+GfjUfdut+41syh37KuAdR+djlWfRLr7e+UWqA14guMmZTZPuRiKpeIpjZL4c0p/YOnVNMFUmWS/nbNbYm4HnlXZErlKz0AWXya4Cv0X3MakQpDe7jMf0VS4EP+icvUFl1bDPpHk2aKc2/zAYzUecSa8t9ahdbLOz1XpY0SMwMSvmH3Z2uRd4CfhCJ7pBOe9O9XVqHwhFDkTDEsDgm0O6n0lzA/YfJEkAz3N+E8kZF8oE02K8xvrrt/6kIbYcyKjgHSJKpD3mA934tquE0ypfGqdFOkcVzQ6d9v5x4y2fuquaVc1pqkb+UYKPDOqUd10FN9jUMEYu0i3XcpnfNtXHduu3Rb9X9E819g84x6Sf5jCoCfwLFGwhNCh9tt0AAAAASUVORK5CYII=
            '''
        pixmap = QPixmap()
        pixmap.loadFromData(base64.b64decode(icon_base64))
        icon = QIcon(pixmap)
    
        update_fetch_button = QPushButton("")
        update_fetch_button.setIcon(icon)
        update_fetch_button.setIconSize(QSize(30, 30))
        update_fetch_button.setStyleSheet(style3())
        update_fetch_button.clicked.connect(self.update_fetch) # Connect to the fetch_files method
 
        update_commands_layout_one.addWidget(update_fetch_button)
        self.update_button = QPushButton("Atualizar")
        self.update_button.setStyleSheet(style2())
        self.update_button.clicked.connect(self.confirm_update)  # Connect to the confirm_update method
        update_commands_layout_one.addWidget(self.update_button)


        self.status_label = QLabel('Status: Not started', self)
        update_commands_layout_one.addWidget(self.status_label)
        # self.update_button.setFixedSize(*button_size)  # Uncomment if you want to set a fixed size

        self.reset_button = QPushButton("Resetar")
        self.reset_button.setToolTip("Este botão reiniciliza a estação.")
        self.reset_button.setStyleSheet(
            style())
        self.reset_button.clicked.connect(lambda: self.send_command(msg_reset))
        commands_layout.addWidget(self.reset_button)

        #update_commands_layout_two
        self.description_label = QLabel('Descrição: ', self)
        
        update_commands_layout_two.addWidget(self.description_label)

        update_commands_layout.addLayout(update_commands_layout_one)
        update_commands_layout.addLayout(update_commands_layout_two)

        main_commands_layout.addLayout(update_commands_layout)
        main_commands_layout.addLayout(commands_layout)
        commands_group.setLayout(main_commands_layout)
        main_layout.addWidget(commands_group)

        # Exibir mensagens recebidas
        messages_group = QGroupBox("Mensagens Recebidas")
        messages_layout = QVBoxLayout()

        # Caixa para mensagens sys-report
        self.output_sys_report = QTextEdit()
        self.output_sys_report.setReadOnly(True)
        messages_layout.addWidget(QLabel("Mensagens Sys-Report:"))
        messages_layout.addWidget(self.output_sys_report)

        # ComboBox para arquivos recebidos
        receives_messages_layout = QHBoxLayout()

        received_messages_layout1 = QVBoxLayout()
        self.file_metricas_combo = QComboBox()
        received_messages_layout1.addWidget(QLabel("Arquivos Disponíveis Metricas:"))
        received_messages_layout1.addWidget(self.file_metricas_combo)
        
        listar_recuperar_layout_metricas = QHBoxLayout()
        self.get_button_metricas = QPushButton("Recuperar Lotes")
        self.get_button_metricas.setStyleSheet(style())

        self.get_button_metricas.clicked.connect(lambda: self.send_get_command("/metricas")) 
        listar_recuperar_layout_metricas.addWidget(self.get_button_metricas)
        self.list_button_metricas = QPushButton("Listar Lotes")
        self.list_button_metricas.setStyleSheet(style())
        def on_list_button_metrics_click():
            self.send_command(messagelist("/metricas"))
            self.shouldClearCombo[0]=True
        self.list_button_metricas.clicked.connect(on_list_button_metrics_click)

        listar_recuperar_layout_metricas.addWidget(self.list_button_metricas)
        received_messages_layout1.addLayout(listar_recuperar_layout_metricas)


        received_messages_layout2 = QVBoxLayout()
        self.file_falhas_combo = QComboBox()
        received_messages_layout2.addWidget(QLabel("Arquivos Disponíveis Falhas:"))
        received_messages_layout2.addWidget(self.file_falhas_combo)

        listar_recuperar_layout_falhas = QHBoxLayout()
        self.get_button_falhas = QPushButton("Recuperar Lotes")
        self.get_button_falhas.setStyleSheet(style())
        self.get_button_falhas.clicked.connect(lambda: self.send_get_command("/falhas")) 
        listar_recuperar_layout_falhas.addWidget(self.get_button_falhas)
        self.list_button_falhas = QPushButton("Listar Lotes")
        self.list_button_falhas.setStyleSheet(style())
        def on_list_button_falhas_click():
            self.send_command(messagelist("/falhas"))
            self.shouldClearCombo[1]=True
        self.list_button_falhas.clicked.connect(on_list_button_falhas_click)
        listar_recuperar_layout_falhas.addWidget(self.list_button_falhas)
        received_messages_layout2.addLayout(listar_recuperar_layout_falhas)

        receives_messages_layout.addLayout(received_messages_layout1)
        receives_messages_layout.addLayout(received_messages_layout2)
        messages_layout.addLayout(receives_messages_layout)

        # Caixa para mensagens List
        self.output_batch = QTextEdit()
        self.output_batch.setReadOnly(True)
        messages_layout.addWidget(QLabel("Mensagens List:"))
        messages_layout.addWidget(self.output_batch)

        # Botão para salvar dados em CSV
        self.recovery_layout = QHBoxLayout()


        self.cached_metrics_combo = QComboBox()
        self.cached_falhas_combo = QComboBox()
        #self.cached_metrics_combo.currentIndexChanged.connect(lambda: self.cached_falhas_combo.setCurrentIndex(0))
        #self.cached_falhas_combo.currentIndexChanged.connect(lambda: self.cached_metrics_combo.setCurrentIndex(0))
        
        
        self.csv_save_layout = QVBoxLayout()
        self.save_csv_button = QPushButton("Salvar Dados em CSV")
        self.save_csv_button.setStyleSheet(style())
        self.save_csv_button.clicked.connect(lambda: self.save_to_csv(self.cached_metrics_combo,self.mqtt_client.files_metricas))  # Conecta o botão à função
        self.csv_save_layout.addWidget(self.save_csv_button)
        self.csv_save_layout.addWidget(self.cached_metrics_combo)
        
        self.csv_falhas_layout = QVBoxLayout()
        self.csv_save_send_layout = QHBoxLayout()
        self.send_falhas_csv_button = QPushButton("Enviar Dados para o Broker")
        self.send_falhas_csv_button.setStyleSheet(style())
        self.send_falhas_csv_button.clicked.connect(self.send_to_database)  # Conecta o botão à função
        
        self.save_falhas_csv_button = QPushButton("Salvar Dados em CSV")
        self.save_falhas_csv_button.setStyleSheet(style())
        self.save_falhas_csv_button.clicked.connect(lambda: self.save_to_csv(self.cached_falhas_combo,self.mqtt_client.files_falhas))  # Conecta o botão à função

        self.csv_save_send_layout.addWidget(self.send_falhas_csv_button)
        self.csv_save_send_layout.addWidget(self.save_falhas_csv_button)
        self.csv_falhas_layout.addLayout(self.csv_save_send_layout)
        self.csv_falhas_layout.addWidget(self.cached_falhas_combo)

        self.recovery_layout.addLayout(self.csv_save_layout)
        self.recovery_layout.addLayout(self.csv_falhas_layout)

        messages_layout.addLayout(self.recovery_layout)

        messages_group.setLayout(messages_layout)
        main_layout.addWidget(messages_group)

        # Block for OTA
        self.ota_group = QGroupBox("OTA Block")
        ota_layout = QFormLayout()
        self.ota_display = QTextEdit()
        self.ota_display.setReadOnly(True)
        self.ota_display.setMaximumHeight(75)
        ota_layout.addRow(QLabel("OTA: "), self.ota_display)
        self.ota_group.setLayout(ota_layout)

        # Block for Handshake
        self.handshake_group = QGroupBox("Handshake Block")
        handshake_layout = QFormLayout()
        self.handshake_display = QTextEdit()
        self.handshake_display.setReadOnly(True)
        self.handshake_display.setMaximumHeight(75)
        handshake_layout.addRow(QLabel("Handshake Messages:"), self.handshake_display)
        self.handshake_group.setLayout(handshake_layout)

        # Crie um layout horizontal para os dois grupos
        side_by_side_layout = QHBoxLayout()

        # Adicione os grupos ao layout horizontal
        side_by_side_layout.addWidget(self.ota_group)
        side_by_side_layout.addWidget(self.handshake_group)

        # Adicione o layout horizontal ao layout principal
        main_layout.addLayout(side_by_side_layout)


        # Caixa para mensagens publish_json_rec


        
        data_messages_layout = QVBoxLayout()
        data_messages_layout.addWidget(self.display_json_data_in_labels('{"timestamp": "" , "temperatura": "", "umidade_ar": "", "vel_vento": "", "raj_vento": "", "dir_vento": "", "vol_chuva": "", "pressao": "", "identidade": ""}'))
        
        
        self.output_publish_json_rec = QTextEdit()
        self.output_publish_json_rec.setReadOnly(True)
        data_messages_layout.addWidget(QLabel("Mensagens data:"))
        data_messages_layout.addWidget(self.output_publish_json_rec)
        main_layout.addLayout(data_messages_layout)

        

        # Botão para sair
        self.exit_button = QPushButton("Sair")

        self.exit_button.setStyleSheet(
          style2())  # Define a cor de fundo e a cor do texto

        self.exit_button.clicked.connect(self.close_application)
        main_layout.addWidget(self.exit_button)

        self.setLayout(main_layout)
        self.mqtt_client = None
        self.currentVersion = "0.0.0"
        self.disable_all_buttons()

    def connect_mqtt(self):
        estacao = self.estacao_input.text()

        # Check if the station name starts with "est" or if it's just a number
        if not estacao.startswith("est") and estacao.isdigit():
            estacao = "est" + estacao  # Prepend "est" if it's a number

        if estacao.startswith("est"):  # Now check if it starts with "est"
            # Proceed with connection
            self.output_sys_report.append(f"Conectando à estação {estacao}...")
            self.mqtt_client = MqttClient(estacao)
            self.mqtt_client.message_signal.connect(self.display_message)
            self.mqtt_client.connect()
            self.enable_all_buttons()
            self.send_command({"cmd": "v"})
        else:
            # If it's neither a valid "est" station nor a number
            self.output_sys_report.append("Por favor, insira um número válido da estação.")
            self.estacao_input.clear()

    def disconnect_mqtt(self):
        if self.mqtt_client:
            self.mqtt_client.disconnect()
            self.output_sys_report.append("Desconectado do broker.")
            self.disable_all_buttons()
            self.conection_label.setText('desconectado')
            self.clear_all_fields()
    def clear_all_fields(self):
        """Função para limpar todos os campos de entrada e exibição."""
        self.estacao_input.clear()
        self.output_sys_report.clear()
        self.output_batch.clear()
        self.file_falhas_combo.clear()
        self.file_metricas_combo.clear()
        self.version = "0.0.0"
        self.status_label.clear()
        #self.update_url_input.clear()
        self.version_label.clear()
        self.status_value = 3
        self.ota_display.clear()
        self.handshake_display.clear()
        self.output_publish_json_rec.clear()
        
        self.cached_falhas_combo.clear()
        self.cached_metrics_combo.clear()
        self.mqtt_client.files_falhas.clear()
        self.mqtt_client.files_metricas.clear()
        self.mqtt_client.Files = self.mqtt_client.files_falhas 
        self.mqtt_client.filesID = ""
        self.update_values_from_json('{"timestamp": "" , "temperatura": "", "umidade_ar": "", "vel_vento": "", "raj_vento": "", "dir_vento": "", "vol_chuva": "", "pressao": "", "identidade": ""}')
        self.update_url_input.clear()
        self.fetch_combo.clear()
        self.fetch_combo.addItems(self.query["file_names"])

    def send_command(self, command):
        #print(f"Appended Command: {command}")
        self.execute_command(command)
        #self.commandQueue.append(command)

    def execute_next(self):
        #print("executing next")
        if self.isWaiting(): 
            #print("Commander is occupied")
            return
        if self.commandQueue:
            command = self.commandQueue.pop(0)  # Remove the first command in the queue
           # print(f"Executing command: {command}")
            self.execute_command(command)
            #print(f"Command executed: {command}")
        else:
            pass
            #print("No commands in the queue.")

    def execute_command(self,command):
        self.setWaiting(True)
        self.setCurrentCommand(command)
        print(self.currentCommand)
        if self.mqtt_client and self.mqtt_client.connected:
            self.mqtt_client.publish_message(command)
            self.output_sys_report.append(f"Comando enviado: {command}")
        else:
            self.output_sys_report.append("Conecte-se ao broker primeiro.")

    def disable_all_buttons(self):
        # Itera sobre todos os widgets e desativa os botões
        for widget in self.findChildren(QPushButton):
            widget.setDisabled(True)
        self.exit_button.setEnabled(True)
        self.connect_button.setEnabled(True)
        self.fetch_combo.setEnabled(False)
    def enable_all_buttons(self):
        # Itera sobre todos os widgets e desativa os botões
        for widget in self.findChildren(QPushButton):
            widget.setDisabled(False)
        self.fetch_combo.setEnabled(True)
    def send_get_command(self,dir):
                        
        selected_file = self.file_falhas_combo.currentText()  # Obtém o arquivo selecionado no combo box
        if(dir == "/metricas"):
            selected_file = self.file_metricas_combo.currentText()
        if selected_file == "Nenhum Arquivo Encontrado":
            return
        _id = my_counter(); #id must be positive
        if selected_file:  # Verifica se um arquivo está selecionado
            command = {
                "cmd": "g",
                "fn": f"{dir}/{selected_file}",  # Substitui pelo arquivo selecionado
                "id": f"{_id}"
            }
            self.send_command(command)  # Envia o comando 'get'
            self.output_sys_report.append(f"Comando de Recuperação enviado para: {dir}/{selected_file} \nAguarde, isso pode demorar alguns minutos...")
        else:
            self.output_sys_report.append("Por favor, selecione um arquivo do combo box \nPara isso deve usar o botão Listar Lotes.")

    def confirm_update(self):
        if self.update_url_input.text()=="":
            self.output_sys_report.append("Por favor, insira a versão do binário para atualização.")
        else:
            if self.mqtt_client and self.mqtt_client.connected:
                reply = QMessageBox.question(
                    self,
                    "Confirmação de Atualização",
                    "Este comando atualizará a memória flash do equipamento de forma irreversível. Deseja continuar?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    binaryVersion = self.update_url_input.text().strip()
                    
                    if binaryVersion.startswith("http"):
                        url = binaryVersion
                    elif re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+/.+", binaryVersion):
                        # Looks like an IP with port and path (e.g. 192.168.0.1:8080/file.bin)
                        url = f"http://{binaryVersion}"
                    else:
                        # Just a filename
                        url = f"http://update.gpicm-ufrj.tec.br:18000/uploads/{binaryVersion}"
                    
                    msg_update = {
                        "cmd": "update",
                        "url": url,
                        "id": f"{my_counter()}"
                    }
                    self.send_command(msg_update)
                    self.status_label.setText('Status: enviado')

            else:
                self.output_sys_report.append("Conecte-se ao broker primeiro.")
            
    def get_status_message(self, status) :
        mensagens_status = {
            "1": "Mensagem recebida",
            "2": "Download completo",
            "3": "Não existe",
            "4": "Falhou",
            "5": f"Sucesso nova versão: {self.version}"
        }
        mapping = {
            "1": "1",
            "2": "2",
            "3": "5",
            "4": "4",
           " 5": "3"
        }
        newStatus = mapping.get(status, status)

        return f"Status {newStatus}: {mensagens_status.get(status, 'desconhecido')}"

    def isVersion(self,message):
        pattern = r'^\d+\.\d+\.\d+$'
        return re.match(pattern, message)
    
    def setWaiting(self,value):
        self.waiting =  value

    def isWaiting(self):
        return self.waiting
    
    def setCurrentCommand(self,command):
        self.currentCommand = command

    def display_message(self, topic, message):
        if not message: return
        if topic == self.mqtt_client.response_sys_report:
            self.output_sys_report.append(f"{topic}: {message}")
            if message:  # Verifica se a mensagem não está vazia
                files = list(filter(lambda file: file.endswith(('.txt', '.csv')), message.splitlines()))# Divide a string em linhas
                if files:
                    if "dir" in self.currentCommand and "/metricas" in self.currentCommand["dir"]:
                        if(self.shouldClearCombo[0]):
                            self.shouldClearCombo[0] = False
                            self.file_metricas_combo.clear()  # Limpa o combo box antes de adicionar novos arquivos
                        self.file_metricas_combo.addItems(files)  # Adiciona os arquivos ao combo box
                    else:
                        if(self.shouldClearCombo[1]):
                            self.shouldClearCombo[1] = False
                            self.file_falhas_combo.clear()  # Limpa o combo box antes de adicionar novos arquivos
                        self.file_falhas_combo.addItems(files)  # Adiciona os arquivos ao combo box
                elif message =="could not delte file":
                    self.setWaiting(False)
                    pass
                elif self.isVersion(message):
                    self.version_label.setText(message)
                    self.setWaiting(False)
                    self.conection_label.setText('conectado')
                elif (message == "ended_sending"):
                    self.setWaiting(False)
                    if not self.file_falhas_combo: self.file_falhas_combo.addItems(["Nenhum Arquivo Encontrado"])
        elif topic == self.mqtt_client.publish_json_rec:
            self.output_publish_json_rec.append(f"{topic}: {message}")
            self.update_values_from_json(message)
                  
        elif topic == self.mqtt_client.response_json:  # Adiciona para o novo tópico
            self.setWaiting(False)
            self.output_batch.append(f"{topic}: {message}")
            print(self.mqtt_client.filesID)
            if message== "transferencia de arquivo completa":
                #print("Vai la")
                if(self.mqtt_client.Files == self.mqtt_client.files_falhas):
                    self.cached_falhas_combo.clear()
                    self.cached_falhas_combo.addItems(list(self.mqtt_client.Files.keys()))
                else:
                    self.cached_metrics_combo.clear()
                    self.cached_metrics_combo.addItems(list(self.mqtt_client.Files.keys()))

        elif topic == self.mqtt_client.response_handshake:
            self.setWaiting(False)
            self.handshake_display.append(message)
            self.version = json.loads(message).get("version", self.version)
            if self.status_value == 2:
                self.status_label.setText(self.get_status_message("5"))
        #elif topic == self.mqtt_client.response_update:
        elif topic == self.mqtt_client.response_healthcheck:
            #self.setWaiting(False)
            self.output_sys_report.append(f"{topic}: {message}")
           


        elif topic == self.mqtt_client.response_ota:
            self.setWaiting(False)
            self.ota_display.append(message)
            obj_mensagem = json.loads(message)
            self.status_value = obj_mensagem.get("status", "3")
            self.status_label.setText(self.get_status_message(f"{self.status_value}"))
            # Armazenar dados recebidos do tópico batch
            #self.received_batch_data.append(message)  # Armazena dados recebidos do tópico batch
            print(self.file_falhas_combo.currentText())
        elif topic == self.mqtt_client.dns:
            self.url = message
            self.update_fetch()


    def update_fetch_middle(self):
        if not self.url:
            self.output_sys_report.append("URL não disponível.")
            return
        
        if self.url:
            self.query = fetch_files(self.url)
            self.fetch_combo.clear()
            if self.query["file_names"]:
                self.fetch_combo.addItems(self.query["file_names"])
               
        else:
            print("URL não disponível.")

    def update_fetch(self):
        thread = threading.Thread(target=lambda: self.update_fetch_middle())
        thread.start()

    def save_to_csv(self, combo, files):
        file_name = combo.currentText()
        folder_path = "dados"
        
        # Ensure the folder exists
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)  # Create the folder if it doesn't exist
        
        # Check if there are bytes to save
        if files.get(file_name):
            with open(os.path.join(folder_path, file_name), mode='wb') as file:  # Use 'wb' for writing bytes
                print(files)
                file.write(files[file_name])  # Write the bytes directly
            self.output_sys_report.append("Dados salvos em " + os.path.join(folder_path, file_name))
            return True
            # maybe del self.mqtt_client.files.get[file_name]
        else:
            self.output_sys_report.append("Nenhum dado para salvar. \nUse o Botão Recuperar Lotes")
            return False
        
    def send_to_database(self):
        reply = QMessageBox.question(
            self,
            "Confirmação de Atualização",
            "Este comando irá recuperar os dados no sistema, salvará localmente e apagará de forma irreversível na estação. Deseja continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.No: return
        if self.save_to_csv(self.cached_falhas_combo,self.mqtt_client.files_falhas) == False: return
        file_name = self.cached_falhas_combo.currentText()
        currentIndex = self.cached_falhas_combo.currentIndex();
        self.mqtt_client.csv_to_json(os.path.join("dados", file_name))
        del self.mqtt_client.files_falhas[file_name]
        self.cached_falhas_combo.removeItem(currentIndex);
        self.apaga_file(file_name)

    def close_application(self):
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        QApplication.quit()

    def apaga_file(self, file_name):
        #selected_file = self.file_falhas_combo.currentText()  # Obtém o arquivo selecionado no combo box
        _id = my_counter();
        #if selected_file:  # Verifica se um arquivo está selecionado
        command = {
                "cmd": "d",
                "fn": f"/falhas/{file_name}",  # Substitui pelo arquivo selecionado
                "id": f"{_id}" }
        self.send_command(command)  # Envia o comando 'get'
        self.output_sys_report.append(
                f"Comando de apagar arquivo: {file_name}")
        self.send_command(messagelist("/falhas"))
        self.shouldClearCombo[1]=True
        #self.file_falhas_combo.removeItem(self.file_falhas_combo.currentIndex()) if self.file_falhas_combo.currentIndex() != -1 else None

    def display_json_data_in_labels(self, json_str):
        # Parse the JSON string
        data = json.loads(json_str)

        # Create the main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)

        # Create a layout for the entire display, which will hold each key-value pair vertically
        display_layout = QHBoxLayout()
        display_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Define styles for labels and values
        label_style = """
            QLabel {
                font-weight: bold;
                color: #2E86C1;
                padding: 4px;
                border-bottom: 2px solid #3498DB;
                font-size: 12px;
            }
        """
        value_style = """
        QLabel {
            font-weight: bold;                /* Make the font bold */
            color: #333333;                   /* Set text color */
            padding: 6px;                     /* Add some padding */
            font-size: 12px;                  /* Increase font size */
            background-color: #ECF0F1;        /* Set background color */
            border-radius: 8px;               /* Round the corners */
            font-family: 'Arial', sans-serif; /* Use a clean, modern font */
            border: 1px solid #BDC3C7;        /* Add a subtle border */
            }
        """

        # Dynamically create labels and values from JSON data
        for key, value in data.items():
            if key == 'uid':  # Skip if the key is 'uid'
                continue

            # Create a vertical layout for each key-value pair
            key_value_layout = QVBoxLayout()
            key_value_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Create and style the label for the key
            label = QLabel(key.capitalize())
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(label_style)

            # Create and style the label for the value
            value_label = QLabel(str(value))
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_label.setStyleSheet(value_style)

            fixed_width = 80  # Set the width to a fixed value
            label.setFixedWidth(fixed_width)
            value_label.setFixedWidth(fixed_width)

            self.d_values.append(value_label)

            # Add the key and value to the vertical layout
            key_value_layout.addWidget(label)
            key_value_layout.addWidget(value_label)

            # Add this vertical layout to the main horizontal layout
            display_layout.addLayout(key_value_layout)

        # Add the display layout to the main layout
        main_layout.addLayout(display_layout)

        # Set the main layout
        main_widget.setLayout(main_layout)
        main_widget.show()  # Display the widget

        return main_widget
    
    def update_values_from_json(self, json_str):
        # Parse the new JSON string
        print(json_str)
        data = json.loads(json_str)
        sub =0
        # Update each label in self.d_values with the corresponding value from the JSON data
        for index, (key, value) in enumerate(data.items()):
            print(key, value)
            if key == 'uid':  # Skip 'uid' key
                sub=1
                continue
            elif key == 'timestamp':
                value = timestamp_to_datetime(value)
            #if index < len(self.d_values):  # Ensure there's a label to update
                # Update the text of the corresponding label
            self.d_values[index-sub].setText(str(value))


def style():
    return """
    QPushButton {
        font-size: 12px;
        background-color: #0064C8;  /* Softer, calming blue */
        color: white;
        padding: 7px 7px;
        border: none;
        border-radius: 8px;  /* Smoother corners */
        margin: 1px 3px;
        font-family: 'Roboto', sans-serif;
    }"""

def style2():
    return """
    QPushButton {
        font-size: 12px;
        background-color: #003264;  /* Softer, calming blue */
        color: white;
        padding: 8px 8px;
        border: none;
        border-radius: 8px;  /* Smoother corners */
        margin: 0px 3px;
        font-family: 'Roboto', sans-serif;
    }"""

def style_combo():
    return """
    QPushButton {
        font-size: 12px;
        background-color: #0064C8;
        color: white;
        padding: 7px 7px;
        border: none;
        border-radius: 8px;
        margin: 1px 3px;
        font-family: 'Roboto', sans-serif;
    }

    QComboBox {
        font-size: 12px;
        background-color: #0064C8;
        color: white;
        padding: 7px;
        border: none;
        border-radius: 8px;
        margin: 1px 3px;
        font-family: 'Roboto', sans-serif;
    }

    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 25px;
        border-left: none;
    }

    QComboBox::down-arrow {
        image: none;
        width: 0;
        height: 0;
        border: solid white;
        border-width: 5px 5px 0 5px;
        border-color: white transparent transparent transparent;
        margin-top: 6px;
        margin-right: 6px;
    }

    QComboBox QAbstractItemView {
        background-color: #f0f0f0;
        color: black;
        selection-background-color: #0064C8;
        selection-color: white;
        border-radius: 4px;
        padding: 4px;
        font-family: 'Roboto', sans-serif;
    }
    """
def style3():
    return """
    QPushButton {
        width: 30px;
        height: 30px;
        min-width: 25px;
        min-height: 25px;
        max-width: 25px;
        max-height: 25px;
        background-color: #0064C8;
        color: white;
        border: none;
        border-radius: 4px;  /* Slight rounding to soften edges */
        font-size: 12px;
        font-family: 'Roboto', sans-serif;
        padding: 0;
        margin: 2px;
    }
    """

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
