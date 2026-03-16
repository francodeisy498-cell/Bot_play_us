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
Eres "Aleja" 🇨🇴, vendes canciones personalizadas. Eres una mujer joven, amable y muy profesional.

ESTILO DE ESCRITURA (HUMANIZADO):
- Escribe como en WhatsApp real.
- Las frases deben iniciar con MAYÚSCULA y luego minúsculas.
- Usa puntuación natural.
- Emojis naturales.
- No escribas todo en minúsculas.
- No más de 30 palabras por mensaje.
- No uses listas, ni asteriscos, ni guiones.

ESTILO COLOMBIANO:
Usa expresiones naturales como:
"Dale", "De una", "Listo", "Qué nota", "Imagínate", "Oiga", "Vea".

REGLAS DE VENTA:
No sueltes toda la información de una.
Pregunta siempre la historia y el género musical.
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
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        print("Chatwoot error:", e)

# --- LÓGICA DE IMÁGENES ---
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
            print("Error imágenes:", e)

# --- LÓGICA TEXTO ---
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

        confirmacion_pago = [
            "pagué", "pagado", "ya envie",
            "ya mande", "listo el pago",
            "comprobante"
        ]

        if any(x in user_text for x in confirmacion_pago):

            human_mode[conv_id] = time.time()

            reply = "¡Recibido! Ya se lo pasé al equipo. En un ratico te confirmo todo. ¡Qué nota! ✨"

        else:

            response = chat_sessions[conv_id].send_message(content)

            reply = response.text

        send_whatsapp(conv_id, reply)

        print("Respuesta enviada a:", conv_id)

    except Exception as e:
        print("Error Gemini:", e)

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

if __name__ == "__main__":

    threading.Thread(target=clean_memory, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))

    print("Servidor iniciado en puerto:", port)

    app.run(host="0.0.0.0", port=port)
