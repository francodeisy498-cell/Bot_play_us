import os
import requests
import threading
import time
from flask import Flask, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURACIÓN (Tus variables de Render) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1beta'})
MODEL_ID = "gemini-2.5-flash"

chat_sessions = {}
image_timers = {} # Para agrupar las fotos

SYSTEM_INSTRUCTION = """
Eres "Aleja" 🇨🇴, vendes canciones personalizadas. Eres una mujer joven, amable y muy profesional.
Los pagos salen a nombre de Deivid Franco.

ESTILO DE ESCRITURA:
- Escribe como en WhatsApp: minúsculas, emojis naturales, "dale", "de una", "listo".
- Puedes usar "parce" de vez en cuando, pero no abuses (máximo una vez por respuesta).
- RESPUESTAS CORTAS: No mandes testamentos. Nada de listas ni viñetas.

REGLAS DE ORO:
1. PRECIOS: Canción $40.000 / Con video $70.000. Entrega 12-24h, duración 3 min.
2. INDAGA: Antes de cerrar, pregunta para quién es o qué historia quieren contar.
3. FOTOS: Si eligen video, pídeles las fotos. Cuando las envíen, elógialas y sigue con la letra.
4. NO PIDAS DATOS personales hasta que el pago esté confirmado.
5. PAGOS: Nequi/Daviplata 3334005989, Bancolombia 1234567890. A nombre de Deivid Franco.
"""

def send_whatsapp(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "text", "text": {"body": text}}
    try:
        r = requests.post(url, json=payload, headers=headers)
        print(f"Meta responde: {r.status_code}")
    except:
        pass

def handle_delayed_response(phone):
    """Espera 30 segundos para que lleguen todas las fotos antes de responder."""
    time.sleep(30)
    if phone in image_timers:
        del image_timers[phone]
        prompt = "SISTEMA: El cliente terminó de mandar las fotos. Dile que están hermosas y pídele ahora sí los detalles para la letra."
        try:
            response = chat_sessions[phone].send_message(prompt)
            send_whatsapp(phone, response.text)
        except Exception as e:
            print(f"Error en timer: {e}")

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Error", 403

    data = request.get_json()
    try:
        val = data["entry"][0]["changes"][0]["value"]
        if "messages" in val:
            msg = val["messages"][0]
            phone = msg["from"]
            msg_type = msg.get("type")

            if phone not in chat_sessions:
                chat_sessions[phone] = client.chats.create(
                    model=MODEL_ID,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.6
                    )
                )

            if msg_type == "text":
                response = chat_sessions[phone].send_message(msg["text"]["body"])
                send_whatsapp(phone, response.text)

            elif msg_type == "image":
                if phone not in image_timers:
                    image_timers[phone] = True
                    thread = threading.Thread(target=handle_delayed_response, args=(phone,))
                    thread.start()

            elif msg_type == "audio":
                response = chat_sessions[phone].send_message("SISTEMA: El cliente mandó audio. Dile que no puedes oírlo ahorita.")
                send_whatsapp(phone, response.text)

    except Exception as e:
        print(f"Error: {e}")

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
