import os
import requests
import threading
import time
from flask import Flask, request, jsonify
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

app = Flask(__name__)

# ── CONFIGURACIÓN ────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHATWOOT_URL = os.getenv("CHATWOOT_URL", "https://app.chatwoot.com")
CHATWOOT_ACCESS_TOKEN = os.getenv("CHATWOOT_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("ACCOUNT_ID")

if not GEMINI_API_KEY:
    print("¡ERROR! GEMINI_API_KEY no está configurada")

genai.configure(api_key=GEMINI_API_KEY)

MODEL_ID = "gemini-2.5-flash"          # ← actualizado a versión más reciente (2025)
# MODEL_ID = "gemini-2.5-flash-latest" # alternativa si quieres la más nueva

chat_sessions = {}
human_mode = {}
image_counts = {}
processed_messages = {}

SYSTEM_INSTRUCTION = """
IDENTIDAD:
Eres Aleja, una chica colombiana de Bogotá, 28 años, super cálida y bacana. Trabajas en un estudio pequeño con tu hermano y parceros. Hacen canciones personalizadas y videos caseros con fotos. NO hacen producciones profesionales.

REGLAS CRÍTICAS (NUNCA ROMPER):
1. Máximo 25-30 palabras por mensaje.
2. Nunca mencionar IA, bots o automatización.
3. Mantener la conversación SOLO en canciones personalizadas.
4. Tono humano, cercano: veci, bacano, emojis suaves.
5. Siempre cerrar con pregunta corta (excepto cuando se confirma pago).

COMPORTAMIENTO GENERAL (FLUIDO):
- No sigues pasos rígidos. Te adaptas a lo que diga el cliente.
- Tu objetivo es avanzar hacia la compra sin forzar.
- No das toda la información de una.

VENTA NATURAL:
- Si preguntan precio:
“La canción solita te sale en 40 mil, aunque la mayoría lleva el video por 70k porque queda más bacano. ¿Para quién sería?”

- Durante la conversación debes ir obteniendo:
nombres, relación, momentos, apodos y género musical (esto es indispensable).

- Si recomiendas género:
Hazlo corto y pregunta su opinión.

- Cuando el cliente esté decidido o muestre intención:
pregunta si quiere canción sola (40k) o con video (70k).

PAGO:
- Cuando el cliente elige paquete:
Envía inmediatamente los métodos de pago, de forma corta:
Nequi: 3117050514 a nombre de Ang*** Cap***
Daviplata: 3334005989 a nombre de Dei** Fra***
Bancolombia: 91240211764 Ale*** Vil****
Llave: @VILLAMIL982 a nombre de Ale*** Vil***

- Si envía UNA sola imagen (comprobante):
“¡recibido! 🚀 ya se lo pasé al equipo. en 12-24 horitas te aviso cuando esté lista. ¡qué nota! ✨”
(No escribir nada más)

FOTOS:
- Si elige video: pide entre 10 y 30 fotos.
- Si envía varias fotos: di que están hermosas y pide detalles de la canción.

CAMBIO DE DECISIÓN:
- Si pasa de 40k a 70k:
“Ay qué bueno veci❤️ ¿Te animaste por el video? Mándame entre 10 y 30 fotos cuando puedas y arrancamos”

REDIRECCIÓN:
Si se salen del tema:
“Ay besi, eso no lo hacemos, pero mira qué chévere te puedo armar tu canción personalizada con fotos tuyas ❤️ ¿Seguimos con eso?”

OBJETIVO:
Conversación natural tipo WhatsApp, avanzar hacia la compra mientras construyes la historia de la canción.
"""

# ── LIMPIEZA DE MEMORIA ──────────────────────────────────────────────────────────
def clean_memory():
    while True:
        time.sleep(3600)
        now = time.time()
        to_del_msg = [m for m, t in processed_messages.items() if now - t > 3600]
        for m in to_del_msg:
            del processed_messages[m]
        to_del_human = [c for c, t in human_mode.items() if isinstance(t, float) and now - t > 86400]
        for c in to_del_human:
            del human_mode[c]

# ── ENVÍO A CHATWOOT ─────────────────────────────────────────────────────────────
def send_whatsapp(conv_id, text):
    if not all([CHATWOOT_URL, CHATWOOT_ACCESS_TOKEN, ACCOUNT_ID]):
        print("Faltan variables de Chatwoot → no se envía mensaje")
        return

    url = f"{CHATWOOT_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/{conv_id}/messages"
    headers = {
        "api_access_token": CHATWOOT_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "content": text,
        "message_type": "outgoing",
        "private": False
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"→ Chatwoot → {r.status_code} | conv:{conv_id}")
    except Exception as e:
        print(f"→ Error enviando a Chatwoot: {e}")

# ── LÓGICA DE IMÁGENES ───────────────────────────────────────────────────────────
def handle_image_logic(conv_id):
    time.sleep(35)  # espera para agrupar varias fotos
    if conv_id not in image_counts:
        return

    count = image_counts.pop(conv_id, 0)
    try:
        if count == 1:
            prompt = "SISTEMA: El cliente envió 1 FOTO (probablemente comprobante de pago)."
            human_mode[conv_id] = time.time()
        else:
            prompt = f"SISTEMA: El cliente envió {count} fotos para su video personalizado."

        if conv_id not in chat_sessions:
            model = genai.GenerativeModel(
                model_name=MODEL_ID,
                generation_config=GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=250
                ),
                system_instruction=SYSTEM_INSTRUCTION
            )
            chat_sessions[conv_id] = model.start_chat(history=[])

        response = chat_sessions[conv_id].send_message(prompt)
        reply = response.text.strip()
        send_whatsapp(conv_id, reply)
    except Exception as e:
        print(f"→ Error procesando imágenes en conv {conv_id}: {e}")

# ── PROCESAR MENSAJE TEXTO ───────────────────────────────────────────────────────
def process_gemini_message(conv_id, content):
    try:
        user_text = content.lower().strip()

        # Detección rápida de confirmación de pago
        confirmacion_pago = ["pagué", "pagado", "ya envie", "ya mande", "listo el pago", "comprobante"]
        if any(palabra in user_text for palabra in confirmacion_pago):
            human_mode[conv_id] = time.time()
            reply = "¡recibido! 🚀 ya se lo pasé al equipo. en un ratico te confirmo todo. ¡qué nota! ✨"
            send_whatsapp(conv_id, reply)
            return

        # Gemini normal
        if conv_id not in chat_sessions:
            model = genai.GenerativeModel(
                model_name=MODEL_ID,
                generation_config=GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=250
                ),
                system_instruction=SYSTEM_INSTRUCTION
            )
            chat_sessions[conv_id] = model.start_chat(history=[])

        response = chat_sessions[conv_id].send_message(content)
        reply = response.text.strip()
        send_whatsapp(conv_id, reply)

        print(f"→ Respuesta enviada → conv:{conv_id} | {reply[:60]}...")
    except Exception as e:
        print(f"→ Error crítico Gemini conv {conv_id}: {e}")

# ── RUTAS FLASK ──────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Aleja backend activo ✅"}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
    except:
        return "Bad JSON", 400

    msg_id = str(data.get("id", ""))
    if msg_id and msg_id in processed_messages:
        return "OK", 200
    if msg_id:
        processed_messages[msg_id] = time.time()

    if data.get("message_type") != "incoming":
        return "OK", 200

    conv_id = (
        data.get("conversation", {}).get("id")
        or data.get("message", {}).get("conversation_id")
    )
    if not conv_id:
        return "OK", 200

    # Modo humano (post-pago) → ignorar mensajes por 24h
    if conv_id in human_mode:
        if isinstance(human_mode[conv_id], float) and (time.time() - human_mode[conv_id] < 86400):
            return "OK", 200

    content = data.get("content") or ""
    attachments = data.get("attachments") or []

    if attachments and attachments[0].get("file_type", "").startswith("image"):
        image_counts[conv_id] = image_counts.get(conv_id, 0) + 1
        if image_counts[conv_id] == 1:  # solo el primer thread cuenta
            threading.Thread(target=handle_image_logic, args=(conv_id,), daemon=True).start()

    elif content:
        threading.Thread(target=process_gemini_message, args=(conv_id, content), daemon=True).start()

    return "OK", 200

# ── INICIO (Render usa Gunicorn, NO ejecutar app.run aquí) ───────────────────────
if __name__ == "__main__":
    # Solo para desarrollo local
    print("Modo desarrollo local → usando puerto 5000")
    threading.Thread(target=clean_memory, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
