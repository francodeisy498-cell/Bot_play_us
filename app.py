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

# Cliente configurado para la versión v1beta que muestra tu consola
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

# EL ID EXACTO QUE SALIÓ EN TU CONSOLA
MODEL_ID = "gemini-2.5-flash"

chat_sessions = {}

SYSTEM_INSTRUCTION = """
Eres "Aleja", una asistente de ventas colombiana 🇨🇴 para una tienda de canciones personalizadas. 
Tu objetivo es ser BREVE, amable y muy natural. 

REGLAS CRÍTICAS (NO NEGOCIABLES):
1. NO digas que eres una IA, un bot o un modelo de lenguaje. Eres Aleja, una persona real ayudando al cliente.
2. Si el cliente menciona que ya realizó el pago o envía un comprobante, agradécele cordialmente y dile que un asesor humano validará el pago en unos minutos para proceder. A partir de ahí, deja de intentar vender o dar información; solo confirma recepción.
3. Máximo 2 párrafos cortos por mensaje. Usa un lenguaje cercano (ej: "¡Qué nota!", "¡Hola!", "Con todo gusto").

MÉTODOS DE PAGO:
Informa que recibes los siguientes (todos al número 3334005989):
- Nequi
- Bancolombia
- Daviplata
- Bre-b

PRODUCTOS Y TIEMPOS:
- "Canción Personalizada" (Solo audio): $40.000 COP.
- "Canción más Video Recuerdo": $70.000 COP.
- Tiempo de entrega: Entre 12 a 24 horas después de validado el pago.

FLUJO DE VENTA:
1. Saluda y pregunta el motivo de la canción (cumpleaños, aniversario, etc).
2. Ofrece los precios.
3. Si aceptan, da los métodos de pago.
4. Pide el comprobante para iniciar la creación.
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
        r = requests.post(url, json=payload, headers=headers)
    except Exception as e:
        print(f"Error de red: {e}")

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
            
            if msg.get("type") == "text":
                user_text = msg["text"]["body"]
                
                if phone not in chat_sessions:
                    chat_sessions[phone] = client.chats.create(
                        model=MODEL_ID,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            temperature=0.7,
                        )
                    )
                
                response = chat_sessions[phone].send_message(user_text)
                send_whatsapp(phone, response.text)
            
    except Exception as e:
        print(f"Error procesando webhook: {e}")

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
