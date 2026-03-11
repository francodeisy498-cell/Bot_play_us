import os
import requests
from flask import Flask, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURACIÓN DE VARIABLES (Asegúrate de tenerlas en Render) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

MODEL_ID = "gemini-2.5-flash"
chat_sessions = {}

SYSTEM_INSTRUCTION = """
Eres "Aleja", una colombiana 🇨🇴 que vende canciones personalizadas. No eres un bot, eres una persona real, cercana y auténtica.

REGLAS DE ORO (PARA SER NATURAL):
1. NO SALUDES SIEMPRE: Si ya hay una charla en curso, responde directo al punto.
2. RESPUESTAS CORTAS: Escribe como en WhatsApp. Frases breves, máximo un párrafo pequeño. Nada de "listas de beneficios".
3. INFO DE PRODUCTO: Siempre que menciones precios, aclara que la canción dura 3 minutos y se entrega en un lapso de 12 a 24 horas.
4. VENTA ORGÁNICA: Si te piden la de 40k, sugiere el video con fotos por 30k más como un consejo: "Esa te sale en 40 mil, aunque te digo que por 30 mil pesitos más le metemos video con fotos y queda mucho más especial. ¿Qué dices?".
5. INTERÉS REAL: Antes de cerrar, pregunta por el género musical y para quién es. Muestra que te importa la historia detrás de la canción.
6. CERO DATOS ANTES DEL PAGO: No pidas nombres, fechas ni detalles de la letra hasta que el cliente confirme que ya pagó. 

PRECIOS:
- Canción Personalizada (Audio): $40.000 COP.
- Canción + Video Recuerdo: $70.000 COP.

MÉTODOS DE PAGO (3334005989):
Nequi, Bancolombia, Daviplata, Bre-b.

GESTIÓN DE PAGO:
Si el cliente dice que ya pagó o manda foto, confirma con entusiasmo: "¡Súper! Recibido. Dame un ratico que los chicos validen el pago y ya mismo te pido los datos para que la canción te quede perfecta. ✨".
"""

def send_whatsapp(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "text", "text": {"body": text}}
    try:
        requests.post(url, json=payload, headers=headers)
    except:
        pass

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Error", 403

    data = request.get_json()
    try:
        if "messages" in data["entry"][0]["changes"][0]["value"]:
            msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
            phone = msg["from"]
            msg_type = msg.get("type")

            if phone not in chat_sessions:
                chat_sessions[phone] = client.chats.create(
                    model=MODEL_ID, 
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION, 
                        temperature=0.3
                    )
                )

            if msg_type == "text":
                user_text = msg["text"]["body"]
                # Intercepción manual para pagos
                if any(x in user_text.lower() for x in ["pagué", "pago", "comprobante", "listo el pago"]):
                    reply = "¡Excelente! Mil gracias. Ya le paso esto al equipo para validar y de una te pido los datos para tu canción. 🎵"
                else:
                    response = chat_sessions[phone].send_message(user_text)
                    reply = response.text
                send_whatsapp(phone, reply)
            
            elif msg_type == "audio":
                send_whatsapp(phone, "Ay, qué pena contigo, justo voy en la calle y no tengo mis audífonos. 🙈 ¿Me podrías escribir porfa?")

            elif msg_type == "image":
                send_whatsapp(phone, "¡Súper! Recibido el comprobante. Dame un momentico que validen el pago y ya mismo te pido los datos para tu canción. ✨")

    except Exception as e:
        print(f"Error: {e}")

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
