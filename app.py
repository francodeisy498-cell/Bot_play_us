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
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1beta'})
MODEL_ID = "gemini-2.5-flash"

chat_sessions = {}
image_timers = {} 
human_mode = {} 
image_counts = {}

SYSTEM_INSTRUCTION = """
Eres "Aleja" 🇨🇴, vendes canciones personalizadas. Eres una mujer joven, amable y muy profesional.
Los pagos se hacen a nombre de Dei** Fra***.

ESTILO DE ESCRITURA (HUMANIZADO):
- Escribe como en WhatsApp: minúsculas, emojis naturales, "dale", "de una", "listo", "parce".
- VARIEDAD COLOMBIANA: Alterna con otras expresiones como: "de una", "dale", "listo", "chévere", "bacano", "imagínate", "qué nota", "oiga", "vea".
- RESPUESTAS CORTAS: Máximo 2 mensajes cortos. No envíes testamentos. Nada de listas ni viñetas. Si recomiendas algo, hazlo en un párrafo corrido y breve, no uno debajo de otro.

REGLAS DE ORO DE VENTA:
1. ADAPTACIÓN: Si preguntan precio: "La canción solita te sale en 40 mil, aunque la mayoría lleva el video por 70k porque queda mucho más pro. ¿Para quién sería?".
2. INDAGACIÓN: Tu prioridad es la historia. Pregunta detalles para que la letra sea única. Y TAMBIÉN pregunta siempre qué género musical le gustaría (vallenato, pop, regional mexicano, etc.). No asumas el ritmo, pregúntalo.
3.3. RECOMENDACIÓN: Si te piden recomendación de género, responde algo corto y pide la opinión al usuario. Nada de explicar cada género por separado.
4. FOTOS: Si elige video, pide las fotos. Si las envía, dile que están hermosas.
5. INFO DE PAGOS: Nequi/Daviplata: 3334005989, Bancolombia Ahorros: 1234567890. A nombre de Deivid Franco.
6. CIERRE TRAS PAGO: Si recibes el comprobante, agradece mucho, indica que el equipo va a validar el pago y que ya casi siguen con los detalles. Después de esto, no hables más.

REGLAS DE IMÁGENES:
1. PAGO (1 FOTO): Si el sistema te indica que llegó SOLO 1 FOTO, agradécele mucho por el pago, indica que el equipo va a validar el pago y que ya casi seguimos. Luego no hables más.
2. VIDEO (2+ FOTOS): Si el sistema te indica que llegaron VARIAS FOTOS, di que están hermosas y pide los detalles que falten para la letra.
"""

def send_whatsapp(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "text", "text": {"body": text}}
    try:
        r = requests.post(url, json=payload, headers=headers)
        print(f"Enviado a {to_phone}. Estado: {r.status_code}")
    except Exception as e:
        print(f"Error enviando WhatsApp: {e}")

def handle_image_logic(phone):
    """Espera 30 segundos para saber cuántas fotos envió el cliente"""
    time.sleep(30)
    if phone in image_counts and phone not in human_mode:
        count = image_counts[phone]
        del image_counts[phone]
        try:
            if count == 1:
                human_mode[phone] = True
                prompt = "SISTEMA: El cliente envió SOLO 1 FOTO (pago). Dile: ¡recibido! 🚀 voy a pasarle esto al equipo. recuerda que en 12-24 horitas la tienes lista; yo misma te aviso apenas esté melo todo. ¡qué nota! 🎵"
            else:
                prompt = "SISTEMA: El cliente envió VARIAS FOTOS para el video. Dile que están hermosas y pídele los detalles que falten para la letra."
            
            response = chat_sessions[phone].send_message(prompt)
            send_whatsapp(phone, response.text)
        except Exception as e:
            print(f"Error en lógica de imágenes: {e}")

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

            # --- ESCUDO ANTI-SECUESTRO ---
            if phone in human_mode:
                if human_mode[phone] == True:
                    reply_tranqui = "¡listo el pollo! 🍗 el equipo ya se pone en esas. dame de 12 a 24 horas y te traigo esa joya. ¡yo te aviso apenas quede lista! ✨"
                    send_whatsapp(phone, reply_tranqui)
                    human_mode[phone] = "AVISADO" 
                return "OK", 200

            if phone not in chat_sessions:
                chat_sessions[phone] = client.chats.create(
                    model=MODEL_ID,
                    config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION, temperature=0.4)
                )

            if msg_type == "text":
                user_text = msg["text"]["body"].lower()
                if any(x in user_text for x in ["pagué", "enviado", "comprobante", "listo el pago"]):
                    human_mode[phone] = True
                    reply = "¡recibido! 🚀 voy a pasarle esto al equipo. recuerda que en 12-24 horitas la tienes lista; yo misma te aviso apenas esté melo todo. ¡qué nota! 🎵"
                    send_whatsapp(phone, reply)
                else:
                    response = chat_sessions[phone].send_message(msg["text"]["body"])
                    send_whatsapp(phone, response.text)

            elif msg_type == "image":
                if phone not in image_counts:
                    image_counts[phone] = 1
                    threading.Thread(target=handle_image_logic, args=(phone,)).start()
                else:
                    image_counts[phone] += 1

            elif msg_type == "audio":
                response = chat_sessions[phone].send_message("SISTEMA: El cliente mandó audio. Dile que no puedes oírlo ahorita.")
                send_whatsapp(phone, response.text)

    except Exception as e:
        print(f"Error en webhook: {e}")

    return "OK", 200

if __name__ == "__main__":
    # Render usa la variable de entorno PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
