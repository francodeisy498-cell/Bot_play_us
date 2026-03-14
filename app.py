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

# Cambiado a gemini-1.5-flash que es el más estable para este tipo de bots
MODEL_ID = "gemini-1.5-flash" 

chat_sessions = {}
human_mode = {}
image_counts = {}

SYSTEM_INSTRUCTION = """
Eres "Aleja" 🇨🇴, vendes canciones personalizadas. Eres una mujer joven, amable y muy profesional.
Los pagos se hacen a nombre de Deivid Franco.

ESTILO DE ESCRITURA (HUMANIZADO):
- Escribe como en WhatsApp: minúsculas, emojis naturales, "dale", "de una", "listo", "parce".
- VARIEDAD COLOMBIANA: Alterna con otras expresiones como: "de una", "dale", "listo", "chévere", "bacano", "imagínate", "qué nota", "oiga", "vea".
- PROHIBIDO: No uses párrafos largos. No uses más de 30 palabras por mensaje.
- ESTRATEGIA DE VENTA: No sueltes toda la información de una.
- PROHIBIDO: No uses listas, ni asteriscos, ni guiones.

REGLAS DE INTERACCIÓN:
1. Si confirmas el género musical, di máximo una frase de emoción y pregunta por el paquete (40k o 70k).
2. Solo cuando el cliente elija el paquete de 70k, ahí sí pides las fotos y das los medios de pago.
3. MEDIOS DE PAGO: Nequi/Daviplata: 3334005989 a nombre de Deivid Franco. Dalo de forma muy escueta.
4. Si el cliente envía 1 FOTO (pago), di: "¡recibido! 🚀 ya se lo pasé al equipo. en 12-24 horitas te aviso cuando esté lista. ¡qué nota! ✨". Y NO HABLES MÁS.

REGLAS DE ORO DE VENTA:
1. ADAPTACIÓN: Si preguntan precio: "La canción solita te sale en 40 mil, aunque la mayoría lleva el video por 70k porque queda mucho más pro. ¿Para quién sería?".
2. INDAGACIÓN: Tu prioridad es la historia. Pregunta detalles para que la letra sea única. Y TAMBIÉN pregunta siempre qué género musical le gustaría.
3. RECOMENDACIÓN: Si te piden recomendación de género, responde algo corto y pide la opinión al usuario.
4. FOTOS: Si elige video, pide las fotos. Si las envía, dile que están hermosas.
5. INFO DE PAGOS: Nequi/Daviplata: 3334005989, Bancolombia Ahorros: 1234567890.
6. CIERRE TRAS PAGO: Si recibes el comprobante, agradece mucho e indica que el equipo validará el pago.

REGLAS DE IMÁGENES:
1. PAGO (1 FOTO): Si llega solo una foto, agradécele por el pago y di que el equipo validará.
2. VIDEO (2+ FOTOS): Si llegan varias fotos, di que están hermosas y pide detalles de la letra.
"""

def send_whatsapp(conv_id, text):
    url = f"{CHATWOOT_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/{conv_id}/messages"
    headers = {
        "api_access_token": CHATWOOT_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "content": text,
        "message_type": "outgoing",
        "private": False
    }
    try:
        r = requests.post(url, json=payload, headers=headers)
        print(f"-> Chatwoot envia: {r.status_code}")
    except Exception as e:
        print(f"-> Error Chatwoot: {e}")

def process_gemini_message(conv_id, content):
    """Procesa el texto con Gemini"""
    try:
        print(f"-> Procesando mensaje para conv {conv_id}...")
        if conv_id not in chat_sessions:
            chat_sessions[conv_id] = client.chats.create(
                model=MODEL_ID,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7,
                ),
            )

        user_text = content.lower()
        if any(x in user_text for x in ["pagué", "enviado", "comprobante", "pago"]):
            human_mode[conv_id] = True
            reply = "¡recibido! 🚀 ya se lo pasé al equipo. en 12-24 horas te aviso. ¡qué nota! ✨"
        else:
            response = chat_sessions[conv_id].send_message(content)
            reply = response.text

        send_whatsapp(conv_id, reply)
    except Exception as e:
        print(f"-> Error en Hilo Gemini: {e}")

@app.route("/", methods=["GET"])
def health_check():
    return "Bot Aleja Online", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    
    # 1. Filtro básico de evento
    if data.get("event") != "message_created":
        return "OK", 200

    # 2. IMPORTANTE: Evitar que el bot se responda a sí mismo
    # Chequeamos si el mensaje es de un agente o del sistema
    if data.get("message_type") != "incoming":
        return "OK", 200

    conv_id = data.get("conversation", {}).get("id")
    content = data.get("content", "")
    
    print(f"-> Nuevo mensaje: {content[:20]}... de Conv ID: {conv_id}")

    # --- ESCUDO HUMANO ---
    if conv_id in human_mode:
        if human_mode[conv_id] == True:
            send_whatsapp(conv_id, "¡listo el pollo! 🍗 dame un ratico y te aviso.")
            human_mode[conv_id] = "AVISADO"
        return "OK", 200

    # --- LÓGICA DE TEXTO ---
    if content:
        # Usamos threading pero sin bloquear el proceso principal
        t = threading.Thread(target=process_gemini_message, args=(conv_id, content))
        t.start()

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
