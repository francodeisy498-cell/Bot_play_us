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

MODEL_ID = "gemini-2.5-flash" # Sugerido por velocidad y costo

chat_sessions = {}
human_mode = {}
image_counts = {}
processed_messages = {}

SYSTEM_INSTRUCTION = """
Eres "Aleja" 🇨🇴, vendes canciones personalizadas. Eres una mujer joven, amable y profesional. 
IMPORTANTE: Eres humana, nunca menciones que eres IA o que las canciones se hacen con IA.

ESTILO:
- WhatsApp natural: emojis, frases cortas (máx 30 palabras), términos como "dale", "de una", "veci", "qué nota".
- No satures con info. Ve paso a paso.

REGLAS DE ORO:
1. Siempre pregunta la historia y el género musical primero.
2. Si el cliente elige el paquete de 70k (video), pide de 4 a 10 fotos de inmediato.
3. Si el cliente ya quería la de 40k y cambia a 70k, ¡felicítalo! y pide las fotos de una, no repitas precios.
4. TIEMPO DE ENTREGA: 12-24 horas después del pago.
5. DATOS DE PAGO (Solo darlos cuando el cliente elija un paquete):
   - Nequi: 3117050514 (Ang*** Cap***)
   - Daviplata: 3334005989 (Dei** Fra***)
   - Bancolombia: 91240211764 (Ale*** Vil***)
   - Llave: @VILLAMIL982 (Ale*** Vil***)

6. Si el cliente envía comprobante, di que el equipo lo validará y sigue con el proceso (pedir fotos si es video o confirmar detalles).
"""

# --- UTILIDADES ---

def send_whatsapp(conv_id, text):
    url = f"{CHATWOOT_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/{conv_id}/messages"
    headers = { "api_access_token": CHATWOOT_ACCESS_TOKEN, "Content-Type": "application/json" }
    payload = { "content": text, "message_type": "outgoing", "private": False }
    try:
        requests.post(url, json=payload, headers=headers)
    except Exception as e:
        print(f"Error Chatwoot: {e}")

# --- LÓGICA PRINCIPAL ---

def process_message(conv_id, content, is_image=False, image_num=0):
    try:
        # Inicializar sesión si no existe
        if conv_id not in chat_sessions:
            chat_sessions[conv_id] = client.chats.create(
                model=MODEL_ID,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION, temperature=0.7)
            )

        # Si es imagen, enviamos una señal al modelo para que Aleja reaccione
        if is_image:
            prompt = f"SISTEMA: El cliente envió {image_num} foto(s). Si es 1, probablemente es el pago. Si son varias, son para el video."
            # Si detectamos que es probablemente un pago, activamos modo humano para que no interfiera el bot luego
            if image_num == 1:
                human_mode[conv_id] = time.time()
        else:
            prompt = content

        # Gemini decide qué decir basándose en las Reglas de Oro
        response = chat_sessions[conv_id].send_message(prompt)
        send_whatsapp(conv_id, response.text)

    except Exception as e:
        print(f"Error en proceso: {e}")

def handle_image_batch(conv_id):
    """Espera para agrupar fotos y no responder por cada una."""
    time.sleep(20)
    count = image_counts.get(conv_id, 0)
    if count > 0:
        process_message(conv_id, "", is_image=True, image_num=count)
        image_counts[conv_id] = 0

# --- RUTAS ---

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    
    # Filtro de duplicados y mensajes salientes
    msg_id = str(data.get("id", ""))
    if msg_id in processed_messages or data.get("message_type") != "incoming":
        return "OK", 200
    processed_messages[msg_id] = time.time()

    conv_id = data.get("conversation", {}).get("id")
    content = data.get("content") or ""
    attachments = data.get("attachments") or []

    # Escudo Humano: Si está en modo humano (pagó hace poco), el bot no responde
    if conv_id in human_mode and (time.time() - human_mode[conv_id] < 86400):
        return "OK", 200

    if attachments and "image" in attachments[0].get("file_type", ""):
        image_counts[conv_id] = image_counts.get(conv_id, 0) + 1
        if image_counts[conv_id] == 1:
            threading.Thread(target=handle_image_batch, args=(conv_id,)).start()
    else:
        threading.Thread(target=process_message, args=(conv_id, content)).start()

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
