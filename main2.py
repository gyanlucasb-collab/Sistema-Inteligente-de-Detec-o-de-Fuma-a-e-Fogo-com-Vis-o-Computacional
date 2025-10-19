# pip install torch torchvision torchaudio transformers pillow opencv-python flask pywin32

import cv2
import time
import os
import threading
import smtplib
import winsound
import win32com.client  # ✅ Biblioteca para fala
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from flask import Flask
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration

# ==============================
# 1. Configurações do e-mail
# ==============================
EMAIL_REMETENTE = "gyanlucasb@gmail.com"
EMAIL_SENHA = "wgbb dicg qzlt romd"  # senha de app do Gmail
EMAIL_DESTINATARIO = "giansoares03@gmail.com"

# ==============================
# 2. Carrega modelo BLIP
# ==============================
processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

# Pasta para salvar capturas
os.makedirs("capturas", exist_ok=True)

# Lista de logs
detec_log = []

# ==============================
# 3. Função de envio de e-mail
# ==============================
def enviar_email(filename, caption):
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_REMETENTE
        msg["To"] = EMAIL_DESTINATARIO
        msg["Subject"] = "🔥 ALERTA: Chama detectada"

        corpo = f"Foi detectada uma chama!\nLegenda: {caption}\nArquivo: {filename}"
        msg.attach(MIMEText(corpo, "plain"))

        # Anexa a foto
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

# ==============================
# 4. Funções de alerta
# ==============================
def tocar_alarme():
    for _ in range(5):
        winsound.Beep(1000, 500)  # frequência 1000 Hz, duração 500 ms

def alerta_voz():
    try:
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Volume = 100
        speaker.Rate = 0
        texto = "PERIGO! Foi detectado um foco de incêndio! Saiam da fábrica imediatamente!"
        speaker.Speak(texto)
    except Exception as e:
        print(f"❌ Erro na fala: {e}")

# ==============================
# 5. Função de salvar e alertar
# ==============================
def save_photo(frame, caption):
    filename = datetime.now().strftime("capturas/fogo_%Y%m%d_%H%M%S.jpg")
    cv2.imwrite(filename, frame)

    log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Fogo detectado → {caption} (Foto salva em {filename})"
    print("\n🔥🔥🔥 ALERTA DE CHAMA DETECTADA 🔥🔥🔥")
    print(log_msg)
    print("=============================================")
    detec_log.append(log_msg)

    # Executa som, fala e e-mail em paralelo
    threading.Thread(target=tocar_alarme, daemon=True).start()
    threading.Thread(target=alerta_voz, daemon=True).start()
    threading.Thread(target=enviar_email, args=(filename, caption), daemon=True).start()

# ==============================
# 6. Servidor Flask
# ==============================
app = Flask(__name__)

@app.route("/")
def index():
    if not detec_log:
        return "<h1>Nenhuma chama detectada ainda 🔍</h1>"
    logs_html = "<br>".join(detec_log[-10:])
    return f"<h1>Detecções de Chama</h1><p>{logs_html}</p>"

def run_server():
    app.run(host="0.0.0.0", port=5000)

# ==============================
# 7. Thread para servidor
# ==============================
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# ==============================
# 8. Ativa a câmera
# ==============================
camera = cv2.VideoCapture(0)
if not camera.isOpened():
    print("❌ Câmera não identificada")
    exit()

print("✅ Câmera ativada. Pressione 'q' para sair.")

# ==============================
# 9. Loop principal
# ==============================
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

    # Exibe legenda
    cv2.putText(frame, f"Legenda: {caption}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2, cv2.LINE_AA)

    # Detecta chama
    if any(word in caption.lower() for word in ["fire", "flame", "candle", "torch", "lighter"]):
        save_photo(frame, caption)
        cv2.putText(frame, "🔥 ALERTA: CHAMA DETECTADA 🔥", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3, cv2.LINE_AA)

    cv2.imshow("Detecção de Fogo (Q para sair)", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

    time.sleep(1)

# ==============================
# 10. Finaliza
# ==============================
camera.release()
cv2.destroyAllWindows()
