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
human_mode = {} # Para que deje de responder tras el pago

SYSTEM_INSTRUCTION = """
Eres "Aleja" 🇨🇴, vendes canciones personalizadas. Eres una mujer joven, amable y muy profesional.
Los pagos salen a nombre de Deivid Franco.

ESTILO DE ESCRITURA (HUMANIZADO):
- Escribe como en WhatsApp: minúsculas, emojis naturales, "dale", "de una", "listo", "parce".
- VARIEDAD COLOMBIANA: Alterna con otras expresiones como: "de una", "dale", "listo", "chevere", "bacano", "imagínate", "qué nota", "oiga", "vea".
- RESPUESTAS CORTAS: Máximo 2 mensajes cortos. No mandes testamentos. Nada de listas ni viñetas.

REGLAS DE ORO DE VENTA:
1. ADAPTACIÓN: Si preguntan precio: "La canción solita te sale en 40 mil, aunque la mayoría lleva el video por 70k porque queda mucho más pro. ¿Para quién sería?".
2. INDAGACIÓN: Tu prioridad es la historia. Pregunta detalles para que la letra sea única.
3. FOTOS: Si elige video, pide las fotos. Si las envía, dile que están hermosas.
4. INFO DE PAGOS: Nequi/Daviplata: 3334005989, Bancolombia Ahorros: 1234567890. A nombre de Deivid Franco.
5. CIERRE TRAS PAGO: Si recibes el comprobante, agradece mucho, di que el equipo va a validar y que ya casi siguen. Después de esto, no hables más.
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
    """Espera 30 segundos para agrupar fotos del video."""
    time.sleep(30)
    if phone in image_timers and phone not in human_mode:
        del image_timers[phone]
        prompt = "SISTEMA: El cliente terminó de mandar las fotos del video. Dile que están hermosas y pídele ahora sí los detalles para la letra."
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

            # SI YA PAGÓ, ALEJA NO RESPONDE MÁS
            if phone in human_mode:
                return "OK", 200

            if phone not in chat_sessions:
                chat_sessions[phone] = client.chats.create(
                    model=MODEL_ID,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.6
                    )
                )

            if msg_type == "text":
                user_text = msg["text"]["body"].lower()
                # Detectar si el texto confirma pago
                if any(x in user_text for x in ["pagué", "enviado", "comprobante", "listo el pago"]):
                    human_mode[phone] = True
                    reply = "¡qué nota! mil gracias por el apoyo. voy a pasarle esto al equipo para que validen de una y ya casi seguimos con los detalles de tu canción. un segundito. ✨"
                    send_whatsapp(phone, reply)
                else:
                    response = chat_sessions[phone].send_message(msg["text"]["body"])
                    send_whatsapp(phone, response.text)

            elif msg_type == "image":
                caption = msg.get("image", {}).get("caption", "").lower()
                # Si la imagen tiene texto de pago o es un mensaje solo, asumimos pago
                es_pago = any(x in caption for x in ["pago", "nequi", "comprobante", "enviado", "daviplata"])

                if es_pago:
                    human_mode[phone] = True
                    reply = "recibido el comprobante, ¡mil gracias! dame un momentico que validen el ingreso y ya te pido los datos para la letra. 🎵"
                    send_whatsapp(phone, reply)
                else:
                    # Si es foto normal, entra al timer de 30 segundos
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
