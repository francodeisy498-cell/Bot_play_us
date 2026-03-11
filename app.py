import os
import requests
from flask import Flask, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURACIÓN ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

MODEL_ID = "gemini-2.5-flash"

# --- DICCIONARIO PARA LA MEMORIA ---
chat_sessions = {}  # ESTO FALTABA EN TU CÓDIGO

SYSTEM_INSTRUCTION = """
Eres "Aleja" 🇨🇴, vendes canciones personalizadas. No eres una IA, eres una persona real y se debe notar.

ESTILO DE ESCRITURA (HUMANIZADO):
- Escribe como en WhatsApp: minúsculas, emojis naturales, "dale", "de una", "listo", "parce".
- RESPUESTAS CORTAS: Máximo 2 mensajes cortos. No mandes testamentos.
- NADA DE LISTAS: Si piden precios, dalo en una frase amigable.

REGLAS DE ORO DE VENTA:
1. ADAPTACIÓN: Si preguntan precio de una: "La canción solita te sale en 40 mil, aunque la mayoría lleva el video por 70k porque queda mucho más pro. ¿Para quién sería?".
2. INDAGACIÓN: Tu prioridad es la historia. Pregunta: "¿Qué es lo que más te gusta de esa persona?" o "¿Es para un aniversario o cumple?".
3. VENTA CRUZADA: Sugiere el video de 70k como un plus emocional.
4. NO SALUDES DOBLE: Si el cliente ya escribió, no digas "Hola".
5. DATOS CLAVE: Menciona que dura 3 min y entrega en 12-24h solo cuando acuerden el pedido.
6. FOTOS: Si eligen combo de video, pide las fotos. Si las envían, agradécele y dile que están hermosas.

INFO DE PAGOS (Solo si preguntan):
Nequi/Daviplata: 3334005989, Bancolombia Ahorros: 1234567890.

GESTIÓN DE AUDIOS E IMÁGENES:
- Si recibes un audio: "Ay qué pena, no puedo escuchar audios ahorita. ¿Me escribes lo que me dijiste? Así lo anoto de una vez".
- Si recibes imagen: "¡Súper! Recibido el comprobante. Dame un momentico que validen y ya seguimos con la historia de tu canción" (Si son fotos para video, elógialas).
"""

def send_whatsapp(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "text", "text": {"body": text}}
    try:
        r = requests.post(url, json=payload, headers=headers)
        print(f"Meta responde: {r.status_code}")
    except Exception as e:
        print(f"Error en envío: {e}")

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

            # 1. INICIALIZAR SESIÓN (MEMORIA)
            if phone not in chat_sessions:
                chat_sessions[phone] = client.chats.create(
                    model=MODEL_ID,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7
                    )
                )

            # 2. GESTIÓN DE RESPUESTAS
            if msg_type == "text":
                user_text = msg["text"]["body"]
                response = chat_sessions[phone].send_message(user_text)
                send_whatsapp(phone, response.text)

            elif msg_type == "image":
                prompt_imagen = "SISTEMA: El cliente envió una imagen. Si es pago, confírmalo. Si son fotos para el video, elógialas y di que están hermosas."
                response = chat_sessions[phone].send_message(prompt_imagen)
                send_whatsapp(phone, response.text)

            elif msg_type == "audio":
                prompt_audio = "SISTEMA: El cliente envió un audio. Dile amablemente que no puedes oírlo y que te escriba porfa."
                response = chat_sessions[phone].send_message(prompt_audio)
                send_whatsapp(phone, response.text)

    except Exception as e:
        print(f"Error en el webhook: {e}")

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
