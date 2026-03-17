import os
import requests
import threading
import time
from flask import Flask, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURACIÓN ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHATWOOT_URL = os.getenv("CHATWOOT_URL", "https://app.chatwoot.com")
CHATWOOT_ACCESS_TOKEN = os.getenv("CHATWOOT_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("ACCOUNT_ID")

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={"api_version": "v1beta"}
)

MODEL_ID = "gemini-2.5-flash" 

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

# --- LIMPIEZA DE MEMORIA ---
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

def send_whatsapp(conv_id, text):
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
        r = requests.post(url, json=payload, headers=headers)
        print(f"-> Chatwoot Status: {r.status_code}")
    except Exception as e:
        print(f"-> Error API Chatwoot: {e}")

# --- LÓGICA DE RESPUESTA ---

def handle_image_logic(conv_id):
    time.sleep(35)

    if conv_id in image_counts:
        count = image_counts[conv_id]
        del image_counts[conv_id]

        try:
            prompt = "SISTEMA: El cliente envió 1 FOTO (pago)." if count == 1 else f"SISTEMA: El cliente envió {count} fotos para su video."

            if count == 1:
                human_mode[conv_id] = time.time()

            if conv_id not in chat_sessions:
                chat_sessions[conv_id] = client.chats.create(
                    model=MODEL_ID,
                    config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
                )

            response = chat_sessions[conv_id].send_message(prompt)
            send_whatsapp(conv_id, response.text)

        except Exception as e:
            print(f"-> Error procesando imágenes: {e}")

def process_gemini_message(conv_id, content):
    try:
        if conv_id not in chat_sessions:
            chat_sessions[conv_id] = client.chats.create(
                model=MODEL_ID,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7,
                    max_output_tokens=250
                )
            )

        user_text = content.lower()
        confirmacion_pago = ["pagué", "pagado", "ya envie", "ya mande", "listo el pago", "comprobante"]

        if any(x in user_text for x in confirmacion_pago):
            human_mode[conv_id] = time.time()
            reply = "¡recibido! 🚀 ya se lo pasé al equipo. en un ratico te confirmo todo. ¡qué nota! ✨"
        else:
            response = chat_sessions[conv_id].send_message(content)
            reply = response.text

        send_whatsapp(conv_id, reply)
        print(f"-> Respuesta enviada a ID: {conv_id}")

    except Exception as e:
        print(f"-> Error Crítico Gemini: {e}")

# --- RUTAS ---

@app.route("/", methods=["GET"])
def health_check():
    return "Servidor de Aleja Activo ✅", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    msg_id = str(data.get("id", ""))
    if msg_id and msg_id in processed_messages:
        return "OK", 200
    if msg_id:
        processed_messages[msg_id] = time.time()

    if data.get("message_type") != "incoming":
        return "OK", 200

    conv_id = data.get("conversation", {}).get("id") or data.get("message", {}).get("conversation_id")
    if not conv_id:
        return "OK", 200

    if conv_id in human_mode:
        t_pago = human_mode[conv_id]
        if isinstance(t_pago, float) and (time.time() - t_pago < 86400):
            return "OK", 200

    content = data.get("content") or ""
    attachments = data.get("attachments") or []

    if attachments and "image" in attachments[0].get("file_type", ""):
        image_counts[conv_id] = image_counts.get(conv_id, 0) + 1

        if image_counts[conv_id] == 1:
            threading.Thread(target=handle_image_logic, args=(conv_id,)).start()

    elif content:
        threading.Thread(target=process_gemini_message, args=(conv_id, content)).start()

    return "OK", 200

# ✅ SOLO AQUÍ VA ESTO (IMPORTANTE)
if __name__ == "__main__":
    threading.Thread(target=clean_memory, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
