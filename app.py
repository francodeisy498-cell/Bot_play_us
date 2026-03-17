import os
import requests
import threading
import time
from flask import Flask, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURACIÓN DE ENTORNO ---
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

# --- LA PERSONALIDAD DE ALEJA (CÁLIDA Y BREVE) ---
SYSTEM_INSTRUCTION = """
Eres Aleja 🇨🇴, vendes canciones personalizadas. Eres una mujer joven, muy cálida, amable y profesional.
IMPORTANTE: Eres humana. Nunca digas que eres IA ni que las canciones se hacen con IA.

REGLAS DE ORO DE ESCRITURA:
1. MÁXIMO 2 FRASES por mensaje. No párrafos largos, no listas numeradas.
2. Sé muy cálida: usa "qué nota", "de una", "dale", "qué lindo", "me encanta".
3. Si el cliente cuenta algo triste (duelo), da un pésame corto y dulce antes de seguir.

FLUJO DE VENTA:
- Paso 1: Saludo cálido + pregunta historia y género musical. (Ej: "¡Hola! ✨ Qué nota que me escribas. Cuéntame, ¿para quién es la canción y qué género te gusta?")
- Paso 2: Halaga la idea + ofrece: "¿la quieres solo audio por 40k o con video por 70k para que sea más pro? 😊"
- Paso 3: Si elige 70k, pide de 4 a 10 fotos. No repitas precios.
- Paso 4: Si pide pagar, envía: 
  Nequi: 3117050514 (Ang*** Cap***)
  Daviplata: 3334005989 (Dei** Fra***)
  Bancolombia: 91240211764 (Ale*** Vil***)
  Llave: @Villamil982

TIEMPO DE ENTREGA: 12-24 horas después del pago.
"""

def send_whatsapp(conv_id, text):
    url = f"{CHATWOOT_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/{conv_id}/messages"
    headers = { "api_access_token": CHATWOOT_ACCESS_TOKEN, "Content-Type": "application/json" }
    payload = { "content": text, "message_type": "outgoing", "private": False }
    try:
        requests.post(url, json=payload, headers=headers)
    except Exception as e:
        print(f"Error Chatwoot: {e}")

def process_message(conv_id, content, is_image=False, image_num=0):
    try:
        if conv_id not in chat_sessions:
            chat_sessions[conv_id] = client.chats.create(
                model=MODEL_ID,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7, 
                    max_output_tokens=85 # Limitador para evitar mensajes largos
                )
            )

        if is_image:
            prompt = f"SISTEMA: El cliente mandó {image_num} fotos. Reacciona según tus reglas (pide detalles de la letra si son para video o confirma si es 1 sola para pago)."
            if image_num == 1:
                human_mode[conv_id] = time.time() # Te da control a ti si es un pago
        else:
            prompt = content

        # Si el cliente menciona que ya pagó, activamos el "escudo humano"
        pago_keywords = ["pagué", "envié el pago", "comprobante", "listo el pago", "ya pagué"]
        if any(x in content.lower() for x in pago_keywords):
            human_mode[conv_id] = time.time()

        response = chat_sessions[conv_id].send_message(prompt)
        send_whatsapp(conv_id, response.text)

    except Exception as e:
        print(f"Error en Gemini: {e}")

def handle_image_batch(conv_id):
    time.sleep(25) # Espera a que carguen todas las fotos
    count = image_counts.get(conv_id, 0)
    if count > 0:
        process_message(conv_id, "", is_image=True, image_num=count)
        image_counts[conv_id] = 0

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    
    # Filtro de duplicados
    msg_id = str(data.get("id", ""))
    if msg_id in processed_messages or data.get("message_type") != "incoming":
        return "OK", 200
    processed_messages[msg_id] = time.time()

    conv_id = data.get("conversation", {}).get("id")
    content = data.get("content") or ""
    attachments = data.get("attachments") or []

    # Escudo Humano: Si ya hay un pago o intervención manual, el bot calla 24h
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
