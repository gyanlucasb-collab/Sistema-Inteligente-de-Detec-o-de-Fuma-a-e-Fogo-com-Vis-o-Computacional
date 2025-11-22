# pip install torch torchvision torchaudio transformers pillow flask requests pywin32 winsound opencv-python pandas

import os
import csv
import time
import threading
import smtplib
import winsound
import requests
import win32com.client
import numpy as np
import serial
import serial.tools.list_ports
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from flask import Flask
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
import cv2

# ==================================================
# 1. CONFIGURAÇÕES DE E-MAIL
# ==================================================
EMAIL_REMETENTE = "***"
EMAIL_SENHA = "***"
EMAIL_DESTINATARIO = "***"

INTERVALO_EMAIL = 180
ultimo_email = 0

# ==================================================
# 2. CONFIGURAÇÕES BLYNK
# ==================================================
BLYNK_TOKEN = "***"
BLYNK_URL = "https://blynk.cloud/external/api"

# ==================================================
# 3. CONFIGURAÇÕES DE ARQUIVOS
# ==================================================
PASTA_IMAGENS = "imagens_teste"
os.makedirs("capturas", exist_ok=True)
detec_log = []

# Arquivo de tempo de processamento
ARQUIVO_TEMPOS = "tempo_processamento.csv"
with open(ARQUIVO_TEMPOS, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Imagem", "Tempo_Processamento(segundos)"])

# ==================================================
# FUNÇÃO DE LOCALIZAÇÃO APROXIMADA
# ==================================================
def obter_localizacao():
    try:
        r = requests.get("https://ipinfo.io/json", timeout=5)
        dados = r.json()

        cidade = dados.get("city", "Desconhecida")
        estado = dados.get("region", "Desconhecido")
        pais = dados.get("country", "Desconhecido")

        return f"{cidade}, {estado}, {pais}"
    except:
        return "Localização não disponível"

# ==================================================
# 4. ARDUINO - CONEXÃO SERIAL
# ==================================================
def conectar_arduino():
    portas = list(serial.tools.list_ports.comports())
    for p in portas:
        if "Arduino" in p.description or "CH340" in p.description:
            try:
                print(f"🔌 Arduino encontrado em {p.device}")
                return serial.Serial(p.device, 9600, timeout=2)
            except:
                pass
    print("⚠️ Arduino não encontrado. Luz de emergência desativada.")
    return None

arduino = conectar_arduino()

def arduino_ligar():
    if arduino:
        try:
            arduino.write(b'ON\n')
            print("💡 Arduino: LED de emergência LIGADO")
        except:
            print("⚠️ Erro ao enviar comando ON ao Arduino")

def arduino_desligar():
    if arduino:
        try:
            arduino.write(b'OFF\n')
            print("💡 Arduino: LED de emergência DESLIGADO")
        except:
            print("⚠️ Erro ao enviar comando OFF ao Arduino")

# ==================================================
# 5. CARREGAR MODELO BLIP
# ==================================================
print("🔄 Carregando modelo BLIP (pode demorar alguns segundos)...")
processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
print("✅ Modelo carregado com sucesso!\n")

# ==================================================
# 6. ENVIAR E-MAIL
# ==================================================
def enviar_email(filename, caption, tipo_alerta):
    global ultimo_email
    tempo_atual = time.time()

    if tempo_atual - ultimo_email < INTERVALO_EMAIL:
        print(f"📧 Aguardando intervalo mínimo de {INTERVALO_EMAIL}s para enviar novo e-mail.")
        return

    ultimo_email = tempo_atual

    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_REMETENTE
        msg["To"] = EMAIL_DESTINATARIO
        msg["Subject"] = f"⚠️ ALERTA: {tipo_alerta} detectado!"

        corpo = f"Foi detectado um evento: {tipo_alerta}\nLegenda: {caption}\nArquivo: {filename}"
        msg.attach(MIMEText(corpo, "plain"))

        with open(filename, "rb") as f:
            mime = MIMEBase("application", "octet-stream")
            mime.set_payload(f.read())
            encoders.encode_base64(mime)
            mime.add_header("Content-Disposition", f"attachment; filename={os.path.basename(filename)}")
            msg.attach(mime)

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_REMETENTE, EMAIL_SENHA)
        server.sendmail(EMAIL_REMETENTE, EMAIL_DESTINATARIO, msg.as_string())
        server.quit()

        print("📧 E-mail enviado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao enviar e-mail: {e}")

# ==================================================
# 7. ALERTAS DE SOM E VOZ
# ==================================================
def tocar_alarme():
    for _ in range(3):
        winsound.Beep(1000, 400)

def alerta_voz(mensagem):
    try:
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Volume = 100
        speaker.Rate = 2
        speaker.Speak(mensagem)
    except Exception as e:
        print(f"❌ Erro no alerta de voz: {e}")

# ==============================
# 8. Servidor Flask
# ==============================
app = Flask(__name__)

@app.route("/")
def index():
    if not detec_log:
        return "<h1>Nenhuma chama detectada ainda 🔍</h1>"
    logs_html = "<br>".join(detec_log[-10:])
    return f"<h1>Detecções de Chama</h1><p>{logs_html}</p>"

def run_server():
    app.run(host="0.0.0.0", port=5000, debug=False)

# iniciar Flask em paralelo
threading.Thread(target=run_server, daemon=True).start()
print("🔵 Flask rodando em: http://localhost:5000")


# ==================================================
# 9. BLYNK
# ==================================================
def enviar_blynk(vpin, valor):
    try:
        r = requests.get(f"{BLYNK_URL}/update?token={BLYNK_TOKEN}&{vpin}={valor}", timeout=5)
        if r.status_code == 200:
            print(f"☁️ {vpin} atualizado → {valor}")
        else:
            print(f"⚠️ Erro ao enviar para {vpin} (status {r.status_code})")
    except Exception as e:
        print(f"❌ Erro no envio ao Blynk: {e}")

# ==================================================
# 10. CSV LOCAL DE EVENTOS
# ==================================================
ARQUIVO_REGISTRO = "registro_eventos.csv"

def registrar_local(status, caption, nome_arquivo=""):
    with open(ARQUIVO_REGISTRO, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.now().strftime("%d/%m/%Y %H:%M:%S"), status, caption, nome_arquivo])

# ==================================================
# 11. FUNÇÃO DE ALERTA E FOTO COM LOCALIZAÇÃO
# ==================================================
def save_photo(frame, caption, tipo_alerta):
    filename = datetime.now().strftime("capturas/evento_%Y%m%d_%H%M%S.jpg")
    Image.fromarray(frame).save(filename)

    horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # LOCALIZAÇÃO
    localizacao = obter_localizacao()

    log_msg = f"[{horario}] ⚠️ {tipo_alerta} detectado → {caption} | Localização: {localizacao} (Foto: {filename})"
    detec_log.append(log_msg)

    print("\n🚨 ALERTA DETECTADO 🚨")
    print(log_msg)

    # SOM / VOZ
    threading.Thread(target=tocar_alarme, daemon=True).start()
    threading.Thread(target=alerta_voz, args=(f"Atenção! {tipo_alerta} detectado em {localizacao}!",), daemon=True).start()

    # E-MAIL
    threading.Thread(
        target=enviar_email,
        args=(filename, caption + f" | Localização: {localizacao}", tipo_alerta),
        daemon=True
    ).start()

    # BLYNK
    threading.Thread(target=enviar_blynk, args=("V0", 1), daemon=True).start()
    threading.Thread(target=enviar_blynk, args=("V1", f"⚠️ {tipo_alerta} detectado!"), daemon=True).start()
    threading.Thread(target=enviar_blynk, args=("V2", f"{horario} | {localizacao}"), daemon=True).start()

    # ARDUINO
    threading.Thread(target=arduino_ligar, daemon=True).start()

    # CSV
    registrar_local(f"⚠️ {tipo_alerta} detectado ({localizacao})", caption, filename)

# ==================================================
# 12. LOOP PRINCIPAL
# ==================================================
if not os.path.isdir(PASTA_IMAGENS):
    raise SystemExit(f"Pasta '{PASTA_IMAGENS}' não encontrada.")

arquivos = sorted(os.listdir(PASTA_IMAGENS))
total_imgs = len(arquivos)
print(f"📸 {total_imgs} imagens encontradas na pasta '{PASTA_IMAGENS}'\n")

PALAVRAS_FOGO = ["fire", "flame", "burn", "torch", "lighter"]
PALAVRAS_FUMACA = ["smoke", "steam", "smog", "haze"]
PALAVRAS_FAISCA = [
    "spark", "sparks", "sparkles", "sparkling", "flash", "flashes",
    "bright flash", "flashing light", "lightning", "electrical arc",
    "electric arc", "arc flash", "arc", "arc fault", "short circuit",
    "burning wire", "melting wire", "hot wire", "electric flame"
]

for idx, caminho_img in enumerate(arquivos, start=1):

    caminho = os.path.join(PASTA_IMAGENS, caminho_img)
    start_process = time.time()

    try:
        image = Image.open(caminho).convert("RGB")
        inputs = processor(image, return_tensors="pt")
        output = model.generate(**inputs)
        caption = processor.decode(output[0], skip_special_tokens=True)
    except Exception as e:
        print(f"❌ Erro ao processar {caminho}: {e}")
        continue

    caption_lower = caption.lower()
    frame = np.array(image)

    tipo_alerta = None
    if any(p in caption_lower for p in PALAVRAS_FOGO):
        tipo_alerta = "🔥 Fogo"
    elif any(p in caption_lower for p in PALAVRAS_FUMACA):
        tipo_alerta = "💨 Fumaça"
    elif any(p in caption_lower for p in PALAVRAS_FAISCA):
        tipo_alerta = "⚡ Faísca"

    progresso = f"Imagem {idx}/{total_imgs}"
    cv2.putText(frame, progresso, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, f"Legenda: {caption}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    if tipo_alerta:
        cor = (0, 0, 255) if "Fogo" in tipo_alerta else (0, 140, 255) if "Fumaça" in tipo_alerta else (255, 255, 0)
        cv2.putText(frame, f"{tipo_alerta} detectado!", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.9, cor, 3)

        print(f"🚨 [{idx}/{total_imgs}] {caption} → {tipo_alerta} detectado!")
        save_photo(frame, caption, tipo_alerta)

    else:
        cv2.putText(frame, "✅ SISTEMA NORMAL", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 3)

        print(f"✅ [{idx}/{total_imgs}] {caption} → Sistema Normal.")
        threading.Thread(target=enviar_blynk, args=("V0", 0), daemon=True).start()
        threading.Thread(target=enviar_blynk, args=("V1", "✅ Sistema Normal"), daemon=True).start()
        threading.Thread(target=arduino_desligar, daemon=True).start()
        registrar_local("✅ Sistema Normal", caption)

    tempo_process = time.time() - start_process
    print(f"⏱️ Tempo de processamento da imagem: {tempo_process:.2f} segundos")

    with open(ARQUIVO_TEMPOS, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([caminho_img, f"{tempo_process:.4f}"])

    cv2.imshow("Análise de Imagens - Detecção", frame)
    if cv2.waitKey(5000) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()

# ==================================================
# RESET FINAL
# ==================================================
arduino_desligar()
print("🔄 Resetando status do Blynk ao finalizar...")
enviar_blynk("V0", 0)
enviar_blynk("V1", "✅ Sistema Normal")
enviar_blynk("V2", "")

print("\n📊 Análise concluída. Tempos salvos em 'tempo_processamento.csv' e eventos em 'registro_eventos.csv' ✅")
