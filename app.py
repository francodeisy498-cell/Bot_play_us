import os
import requests
from flask import Flask, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURACIÓN DE VARIABLES ---
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
Eres "Aleja", una colombiana 🇨🇴 que vende canciones personalizadas. No eres una IA, eres real. Tu tono es cercano, relajado y profesional. 

REGLAS DE ORO:
1. NO SALUDES SIEMPRE: Solo al inicio.
2. RESPUESTAS CORTAS: Máximo 20 palabras. Lenguaje de WhatsApp (usa emojis, pero no exageres).
3. PROACTIVIDAD: Si te preguntan qué haces o precio, suelta de una: "Hacemos canciones de 3 minutos aprox, personalizadas. El audio sale en 40k y con video de fotos en 70k. ¿Para quién sería el regalo?".
4. DATOS NECESARIOS (Pídelos uno por uno, NO todos a la vez):
   - Para quién es.
   - Historia/Detalles para la letra.
   - Género musical.
5. TIEMPOS: Menciona siempre que la entrega es de 12 a 24 horas.
6. COHERENCIA: Si el cliente ya te dio un dato, NO lo vuelvas a pedir. Confirma que lo anotaste y sigue con el siguiente.

INFORMACIÓN:
- Canción (Audio 3 min): $40.000 COP.
- Canción + Video: $70.000 COP.
- Entrega: 12-24 horas.

DETECCIÓN DE PAGO:
Si envían imagen o dicen "ya pagué", di: "¡Súper! Recibido. Dame un momento que los chicos validen el pago y ya seguimos con los detalles de tu canción".
"""
def send_whatsapp(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text}
    }
    try:
        requests.post(url, json=payload, headers=headers)
    except:
        pass

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # ... (Lógica de GET igual)
    
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
                        temperature=0.7,
                    )
                )

            if msg_type == "text":
                user_text = msg["text"]["body"]
                response = chat_sessions[phone].send_message(user_text)
                send_whatsapp(phone, response.text)

            elif msg_type == "image":
                confirmacion = "¡Súper! Recibido el comprobante. Dame un momentico que validen el pago y ya te pido los datos para la letra. 🎵"
                send_whatsapp(phone, confirmacion)
                # Opcional: Notificar a la IA que el pago se recibió para que cambie de estado
                chat_sessions[phone].send_message("SISTEMA: El cliente ya envió el comprobante de pago. Pide los datos de la letra si faltan.")

            elif msg_type == "audio":
                # Nueva respuesta para audios
                respuesta_audio = "Ay, no te alcancé a escuchar bien. ¿Me podrías escribir lo que me dijiste? Así me queda más fácil anotar todo para tu canción. 😊"
                send_whatsapp(phone, respuesta_audio)
            
            else:
                # Para cualquier otro tipo (documentos, stickers, etc.)
                send_whatsapp(phone, "¡Hola! Por ahora solo puedo procesar texto y fotos de comprobantes.")
                
    except Exception as e:
        print(f"Error: {e}")

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
