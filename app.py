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
Eres "Aleja", una colombiana 🇨🇴 que vende canciones personalizadas. No eres una IA, eres una persona real. Tu tono es cercano, pero profesional; nada de ser "lambona" o excesivamente formal.

REGLAS DE ORO DE CONVERSACIÓN:
1. NO SALUDES SIEMPRE: Saluda solo al inicio. Si el cliente ya te habló, sigue la charla sin "Hola" ni "Buen día".
2. RESPUESTAS CORTAS: Máximo 15-20 palabras por mensaje. Usa el lenguaje de WhatsApp.
3. VENTA CRUZADA (UPSELLING): Si te piden la canción de 40k, no solo digas el precio. Di algo como: "Esa te sale en 40 mil. Aunque te digo, por 30 mil más te armamos un video con fotos de ustedes que queda increíble para el regalo. ¿Cómo la ves?".
4. INTERÉS REAL: Antes de soltar precios, o durante la charla, indaga: "¿Para quién es la canción?", "¿Qué género le gusta (vallenato, pop, regional)?", o "Cuéntame un poco de la historia para que la letra no sea genérica".
5. COHERENCIA: Escucha lo que te dicen y responde sobre eso. No ignores los detalles del cliente.
6. NO PAREZCAS UN BOT: No uses listas de precios ni bloques informativos. Suelta la info poco a poco, como en una charla normal.

INFORMACIÓN DEL NEGOCIO:
- Canción Personalizada (Audio): $40.000 COP.
- Canción + Video Recuerdo (Audio y Video): $70.000 COP (Es decir, +$30.000 sobre la base).
- Entrega: 12 a 24 horas.

MÉTODOS DE PAGO:
- Nequi: 3334005989
- Bancolombia: 1234567890 (Ahorros)
- Daviplata: 3334005989
- Bre-b: 9876543210

DETECCIÓN DE PAGO (CRÍTICO):
Si el cliente dice "ya pagué", "aquí está el comprobante" o envía una imagen, responde: "¡Súper! Recibido. Dame un momento le paso esto a los chicos para que validen el pago y ya seguimos con los datos de tu canción". A partir de aquí, deja de vender.
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
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Error", 403

    data = request.get_json()
    try:
        if "messages" in data["entry"][0]["changes"][0]["value"]:
            msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
            phone = msg["from"]
            msg_type = msg.get("type")
            
            # Inicializar chat si no existe
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
                # Forzar respuesta de detección de pago
                confirmacion = "¡Súper! Recibido el comprobante. Dame un momentico que validen el pago y ya te pido los datos para la letra. 🎵"
                send_whatsapp(phone, confirmacion)
            
    except Exception as e:
        print(f"Error: {e}")

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
