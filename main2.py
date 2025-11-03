
import cv2
import time
import os
import threading
import smtplib
import winsound
import requests
import win32com.client
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from flask import Flask
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration

# ==================================================
# 1. CONFIGURAÇÕES DE E-MAIL
# ==================================================
EMAIL_REMETENTE = "gyanlucasb@gmail.com"
EMAIL_SENHA = "wgbb dicg qzlt romd"  # senha de app do Gmail
EMAIL_DESTINATARIO = "giansoares03@gmail.com"

# ==================================================
# 2. CONFIGURAÇÕES DO BLYNK (IoT)
# ==================================================
BLYNK_TOKEN = "nrJWcz502ksNlx-YR69ywYxu48vewpQy"  
BLYNK_URL = "https://blynk.cloud/external/api"

# ==================================================
# 3. CARREGA MODELO BLIP (Legenda de imagem)
# ==================================================
processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

# Pasta para salvar capturas
os.makedirs("capturas", exist_ok=True)

# Lista de logs
detec_log = []

# ==================================================
# 4. ENVIO DE E-MAIL
# ==================================================
def enviar_email(filename, caption):
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_REMETENTE
        msg["To"] = EMAIL_DESTINATARIO
        msg["Subject"] = "🔥 ALERTA: Chama detectada"

        corpo = f"Foi detectada uma chama!\nLegenda: {caption}\nArquivo: {filename}"
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
# 5. FUNÇÕES DE ALERTA
# ==================================================
def tocar_alarme():
    for _ in range(5):
        winsound.Beep(1000, 500)

def alerta_voz():
    try:
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Volume = 100
        speaker.Rate = 0
        speaker.Speak("PERIGO! Foi detectado um foco de incêndio! Saiam da fábrica!")
    except Exception as e:
        print(f"❌ Erro no alerta de voz: {e}")

# ==================================================
# 6. CONEXÃO COM O BLYNK
# ==================================================
def enviar_dados_iot(valor):
    """Envia valor (0 ou 1) ao Blynk"""
    try:
        r = requests.get(f"{BLYNK_URL}/update?token={BLYNK_TOKEN}&V0={valor}", timeout=5)
        if r.status_code == 200:
            print(f"☁️ Valor {valor} enviado para Blynk (V0).")
        else:
            print(f"⚠️ Falha ao enviar para IoT (status {r.status_code})")
    except Exception as e:
        print(f"❌ Erro ao enviar para IoT: {e}")

def ler_dado_iot():
    """Lê o valor atual do Blynk"""
    try:
        r = requests.get(f"{BLYNK_URL}/get?token={BLYNK_TOKEN}&V0", timeout=5)
        if r.status_code == 200:
            return r.text.strip()
        return f"Erro ({r.status_code})"
    except Exception as e:
        return f"Falha: {e}"

# ==================================================
# 7. FUNÇÃO DE SALVAMENTO E ALERTAS
# ==================================================
def save_photo(frame, caption):
    filename = datetime.now().strftime("capturas/fogo_%Y%m%d_%H%M%S.jpg")
    cv2.imwrite(filename, frame)

    log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Fogo detectado → {caption} (Foto: {filename})"
    detec_log.append(log_msg)
    print("\n🔥🔥🔥 ALERTA DE CHAMA DETECTADA 🔥🔥🔥")
    print(log_msg)
    print("=============================================")

    # Aciona alertas simultâneos
    threading.Thread(target=tocar_alarme, daemon=True).start()
    threading.Thread(target=alerta_voz, daemon=True).start()
    threading.Thread(target=enviar_email, args=(filename, caption), daemon=True).start()
    threading.Thread(target=enviar_dados_iot, args=(1,), daemon=True).start()  # Envia 1 para o Blynk

# ==================================================
# 8. SERVIDOR FLASK PARA MONITORAMENTO LOCAL
# ==================================================
app = Flask(__name__)

@app.route("/")
def index():
    logs_html = "<br>".join(detec_log[-10:]) if detec_log else "Nenhuma chama detectada 🔍"
    valor_blynk = ler_dado_iot()
    return f"""
    <h1>🔥 Sistema de Detecção de Fogo com IoT (Blynk) 🔥</h1>
    <h3>Últimos alertas:</h3>
    <p>{logs_html}</p>
    <h3>📡 Valor atual no Blynk (V0): {valor_blynk}</h3>
    <p><a href="https://blynk.cloud/dashboard" target="_blank">Abrir painel Blynk</a></p>
    """

def run_server():
    app.run(host="0.0.0.0", port=5000)

threading.Thread(target=run_server, daemon=True).start()

# ==================================================
# 9. ATIVAÇÃO DA CÂMERA
# ==================================================
camera = cv2.VideoCapture(0)
if not camera.isOpened():
    print("❌ Câmera não identificada")
    exit()

print("✅ Câmera ativada. Pressione 'q' para sair.")

# ==================================================
# 10. LOOP PRINCIPAL
# ==================================================
ultimo_envio = time.time()
intervalo_envio = 10       # intervalo padrão em segundos
intervalo_pos_fogo = 25    # intervalo após detectar fogo

while True:
    ret, frame = camera.read()
    if not ret:
        print("❌ Erro ao capturar imagem")
        break

    img_path = "temp.jpg"
    cv2.imwrite(img_path, frame)

    image = Image.open(img_path).convert("RGB")
    inputs = processor(image, return_tensors="pt")
    output = model.generate(**inputs)
    caption = processor.decode(output[0], skip_special_tokens=True)

    cv2.putText(frame, f"Legenda: {caption}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2, cv2.LINE_AA)

    fogo_detectado = any(palavra in caption.lower() for palavra in ["fire", "flame", "candle", "torch", "lighter"])

    # Atualiza Blynk de tempos em tempos
    tempo_atual = time.time()
    if tempo_atual - ultimo_envio >= intervalo_envio:
        if fogo_detectado:
            save_photo(frame, caption)
            cv2.putText(frame, "🔥 ALERTA: CHAMA DETECTADA 🔥", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3, cv2.LINE_AA)
            intervalo_envio = intervalo_pos_fogo  # espera mais após fogo
        else:
            threading.Thread(target=enviar_dados_iot, args=(0,), daemon=True).start()
            intervalo_envio = 10  # volta ao padrão se está tudo normal
        ultimo_envio = tempo_atual

    cv2.imshow("Detecção de Fogo (Q para sair)", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

camera.release()
cv2.destroyAllWindows()
