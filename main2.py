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
EMAIL_REMETENTE = "gyanlucasb@gmail.com"
EMAIL_SENHA = "wgbb dicg qzlt romd"
EMAIL_DESTINATARIO = "giansoares03@gmail.com"

INTERVALO_EMAIL = 60
ultimo_email = 0

# ==================================================
# 2. CONFIGURAÇÕES BLYNK
# ==================================================
BLYNK_TOKEN = "nrJWcz502ksNlx-YR69ywYxu48vewpQy"
BLYNK_URL = "https://blynk.cloud/external/api"

# ==================================================
# 3. CONFIGURAÇÕES DE ARQUIVOS
# ==================================================
PASTA_IMAGENS = "imagens_teste"
os.makedirs("capturas", exist_ok=True)
detec_log = []

# ==================================================
# 4. CARREGAR MODELO BLIP
# ==================================================
print("🔄 Carregando modelo BLIP (pode demorar alguns segundos)...")
processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
print("✅ Modelo carregado com sucesso!\n")

# ==================================================
# 5. FUNÇÕES DE E-MAIL
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
# 6. ALERTAS DE SOM E VOZ
# ==================================================
def tocar_alarme():
    for _ in range(3):
        winsound.Beep(1000, 400)

def alerta_voz(mensagem):
    try:
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Volume = 100
        speaker.Rate = 0
        speaker.Speak(mensagem)
    except Exception as e:
        print(f"❌ Erro no alerta de voz: {e}")

# ==================================================
# 7. FUNÇÕES BLYNK
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
# 8. CSV LOCAL
# ==================================================
ARQUIVO_REGISTRO = "registro_eventos.csv"

def registrar_local(status, caption, nome_arquivo=""):
    with open(ARQUIVO_REGISTRO, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.now().strftime("%d/%m/%Y %H:%M:%S"), status, caption, nome_arquivo])

# ==================================================
# 9. SALVAR FOTO E ALERTAS
# ==================================================
def save_photo(frame, caption, tipo_alerta):
    filename = datetime.now().strftime("capturas/evento_%Y%m%d_%H%M%S.jpg")
    Image.fromarray(frame).save(filename)

    horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    log_msg = f"[{horario}] ⚠️ {tipo_alerta} detectado → {caption} (Foto: {filename})"
    detec_log.append(log_msg)

    print("\n🚨 ALERTA DETECTADO 🚨")
    print(log_msg)

    threading.Thread(target=tocar_alarme, daemon=True).start()
    threading.Thread(target=alerta_voz, args=(f"Atenção! {tipo_alerta} detectado!",), daemon=True).start()
    threading.Thread(target=enviar_email, args=(filename, caption, tipo_alerta), daemon=True).start()

    threading.Thread(target=enviar_blynk, args=("V0", 1), daemon=True).start()
    threading.Thread(target=enviar_blynk, args=("V1", f"⚠️ {tipo_alerta} detectado!"), daemon=True).start()
    threading.Thread(target=enviar_blynk, args=("V2", horario), daemon=True).start()

    registrar_local(f"⚠️ {tipo_alerta} detectado", caption, filename)

# ==================================================
# 10. LOOP PRINCIPAL
# ==================================================
if not os.path.isdir(PASTA_IMAGENS):
    raise SystemExit(f"Pasta '{PASTA_IMAGENS}' não encontrada.")

arquivos = sorted(os.listdir(PASTA_IMAGENS))
total_imgs = len(arquivos)
print(f"📸 {total_imgs} imagens encontradas na pasta '{PASTA_IMAGENS}'\n")

PALAVRAS_FOGO = ["fire", "flame", "burn", "torch", "lighter"]
PALAVRAS_FUMACA = ["smoke", "steam", "smog", "haze"]
PALAVRAS_FAISCA = ["spark", "flash", "lightning", "glow", "electric arc"]

# VARIÁVEIS DE TEMPO
tempo_inicio_sistema = time.time()
tempos_detectados = []
primeiro_alerta_registrado = False

for idx, caminho_img in enumerate(arquivos, start=1):

    caminho = os.path.join(PASTA_IMAGENS, caminho_img)

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

    cv2.putText(frame, f"Legenda: {caption}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    if tipo_alerta:

        # Registrar tempo da detecção
        tempo_evento = time.time() - tempo_inicio_sistema
        tempos_detectados.append(tempo_evento)

        if not primeiro_alerta_registrado:
            print(f"⏱️ Tempo até a primeira detecção: {tempo_evento:.2f} segundos")
            primeiro_alerta_registrado = True

        cor = (0, 0, 255) if "Fogo" in tipo_alerta else (0, 140, 255) if "Fumaça" in tipo_alerta else (255, 255, 0)
        cv2.putText(frame, f"{tipo_alerta} detectado!", (10, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, cor, 3)

        print(f"🚨 [{idx}/{total_imgs}] {caption} → {tipo_alerta} detectado!")
        save_photo(frame, caption, tipo_alerta)

    else:
        cv2.putText(frame, "✅ SISTEMA NORMAL", (10, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 3)

        print(f"✅ [{idx}/{total_imgs}] {caption} → Sistema Normal.")
        threading.Thread(target=enviar_blynk, args=("V0", 0), daemon=True).start()
        threading.Thread(target=enviar_blynk, args=("V1", "✅ Sistema Normal"), daemon=True).start()
        registrar_local("✅ Sistema Normal", caption)

    cv2.imshow("Análise de Imagens - Detecção", frame)
    if cv2.waitKey(5000) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()

# 🔵 CALCULAR MÉDIA FINAL
if tempos_detectados:
    media_tempo = sum(tempos_detectados) / len(tempos_detectados)
    print(f"\n⏱️ Tempo médio até as detecções: {media_tempo:.2f} segundos")
else:
    print("\nℹ️ Nenhum alerta foi detectado.")

# ==================================================
# RESET FINAL DO BLYNK
# ==================================================
print("🔄 Resetando status do Blynk ao finalizar...")
enviar_blynk("V0", 0)
enviar_blynk("V1", "✅ Sistema Normal")
enviar_blynk("V2", "")

print("\n📊 Análise concluída. Registros salvos em 'registro_eventos.csv' ✅")
