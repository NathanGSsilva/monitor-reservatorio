import binascii
import json
import network
import ntptime
import os
import socket
import ssl

from machine import Pin, time_pulse_us
from time import sleep_ms, sleep_us, ticks_diff, ticks_ms

from ca_cert import ca_der
from config import API_HOST, DEVICE_ID, INTERVALO_MS, INGEST_KEY




DISTANCIA_CHEIO_CM = 10
DISTANCIA_VAZIO_CM = 110
LIMITE_ALERTA_PCT = 20


trig = Pin(12, Pin.OUT, value=0)
echo = Pin(14, Pin.IN)

wifi = network.WLAN(network.STA_IF)
tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
tls.verify_mode = ssl.CERT_REQUIRED
tls.load_verify_locations(cadata=ca_der())

relogio_sincronizado = False
id_execucao = binascii.hexlify(os.urandom(8)).decode()
contador = 0


def medir_distancia():
    trig.on()
    sleep_us(10)
    trig.off()

    duracao_us = time_pulse_us(echo, 1, 30_000)
    if duracao_us <= 0:
        return None

    return duracao_us / 58


def calcular_nivel(distancia_cm):
    faixa_cm = DISTANCIA_VAZIO_CM - DISTANCIA_CHEIO_CM
    nivel = 100 * (DISTANCIA_VAZIO_CM - distancia_cm) / faixa_cm
    return round(max(0, min(100, nivel)), 1)


def preparar_rede():
    global relogio_sincronizado

    if not wifi.isconnected():
        print("Conectando ao Wokwi-GUEST...")
        wifi.active(False)
        sleep_ms(300)
        wifi.active(True)
        wifi.connect("Wokwi-GUEST", "")

        inicio = ticks_ms()
        while not wifi.isconnected():
            if ticks_diff(ticks_ms(), inicio) >= 30_000:
                raise OSError(f"Tempo limite do Wi-Fi | status={wifi.status()}")
            sleep_ms(100)

        print("Wi-Fi conectado | IP:", wifi.ifconfig()[0])

    if not relogio_sincronizado:
        print("Sincronizando relógio...")
        ntptime.timeout = 5
        ntptime.settime()
        relogio_sincronizado = True
        print("Relógio sincronizado")


def enviar_leitura(leitura, chave):
    corpo = json.dumps(leitura).encode()
    cabecalho = (
        "POST /functions/v1/ingest HTTP/1.1\r\n"
        f"Host: {API_HOST}\r\n"
        f"x-ingest-key: {chave}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(corpo)}\r\n"
        "Connection: close\r\n\r\n"
    )

    endereco = socket.getaddrinfo(
        API_HOST, 443, socket.AF_INET, socket.SOCK_STREAM
    )[0][-1]

    conexao = socket.socket()
    try:
        conexao.settimeout(12)
        conexao.connect(endereco)
        print("TCP conectado")

        conexao = tls.wrap_socket(conexao, server_hostname=API_HOST)
        print("TLS conectado")

        conexao.write(cabecalho.encode() + corpo)
        print("POST enviado, aguardando resposta")

        linha = conexao.readline().split()
        if len(linha) < 2:
            raise OSError("Resposta HTTP incompleta")

        return int(linha[1])
    finally:
        conexao.close()


chave = INGEST_KEY.strip()

if not chave:
    chave = input(
        "Cole a INGEST_KEY e pressione Enter (vazio = teste local): "
    ).strip()

while True:
    inicio = ticks_ms()
    distancia = medir_distancia()

    if distancia is None:
        print("Falha na leitura: sem eco do sensor.")
    else:
        nivel = calcular_nivel(distancia)
        status = "NÍVEL BAIXO" if nivel <= LIMITE_ALERTA_PCT else "NORMAL"
        print(f"Distância: {distancia:.1f} cm | Nível: {nivel:.1f}% | {status}")

        if chave:
            contador += 1
            leitura = {
                "device_id": DEVICE_ID,
                "message_id": f"{id_execucao}-{contador}",
                "distance_cm": round(distancia, 1),
                "level_pct": nivel,
            }

            try:
                preparar_rede()
                codigo = enviar_leitura(leitura, chave)
                print(f"API HTTP {codigo} | envio {leitura['message_id']}")
            except OSError as erro:
                print("Falha no envio:", erro)

    tempo_restante = INTERVALO_MS - ticks_diff(ticks_ms(), inicio)
    if tempo_restante > 0:
        sleep_ms(tempo_restante)

#esse é o certo