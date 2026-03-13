import os
import requests
import threading
import time
from flask import Flask, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURACIÓN CHATWOOT ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHATWOOT_URL = os.getenv("CHATWOOT_URL", "https://app.chatwoot.com")
CHATWOOT_ACCESS_TOKEN = os.getenv("CHATWOOT_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("ACCOUNT_ID")

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={"api_version": "v1beta"}
)

MODEL_ID = "gemini-2.0-flash" # Versión estable

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
2. INDAGACIÓN: Tu prioridad es la historia. Pregunta detalles para que la letra sea única. Y TAMBIÉN pregunta siempre qué género musical le gustaría (vallenato, pop, regional mexicano, etc.). No asumas el ritmo, pregúntalo.
3. RECOMENDACIÓN: Si te piden recomendación de género, responde algo corto y pide la opinión al usuario. Nada de explicar cada género por separado.
4. FOTOS: Si elige video, pide las fotos. Si las envía, dile que están hermosas.
5. INFO DE PAGOS: Nequi/Daviplata: 3334005989, Bancolombia Ahorros: 1234567890. A nombre de Deivid Franco.
6. CIERRE TRAS PAGO: Si recibes el comprobante, agradece mucho, indica que el equipo va a validar el pago y que ya casi siguen con los detalles. Después de esto, no hables más.

REGLAS DE IMÁGENES:
1. PAGO (1 FOTO): Si el sistema te indica que llegó SOLO 1 FOTO, agradécele mucho por el pago, indica que el equipo va a validar el pago y que ya casi seguimos. Luego no hables más.
2. VIDEO (2+ FOTOS): Si el sistema te indica que llegaron VARIAS FOTOS, di que están hermosas y pide los detalles que falten para la letra.
"""

def send_whatsapp(conv_id, text):
    """Envía el mensaje a través de la API de Chatwoot"""
    url = f"{CHATWOOT_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/{conv_id}/messages"
    headers = {
        "api_access_token": CHATWOOT_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }
    payload = {
        "content": text,
        "message_type": "outgoing",
    }
    try:
        r = requests.post(url, json=payload, headers=headers)
        print(f"Enviado a Conv {conv_id}. Estado: {r.status_code}")
    except Exception as e:
        print(f"Error enviando a Chatwoot: {e}")

def handle_image_logic(conv_id):
    """Espera 30 segundos para saber cuántas fotos envió el cliente"""
    time.sleep(30)
    if conv_id in image_counts and conv_id not in human_mode:
        count = image_counts[conv_id]
        del image_counts[conv_id]
        try:
            if count == 1:
                human_mode[conv_id] = True
                prompt = "SISTEMA: El cliente envió SOLO 1 FOTO (pago). Dile: ¡recibido! 🚀 voy a pasarle esto al equipo. recuerda que en 12-24 horitas la tienes lista; yo misma te aviso apenas esté melo todo. ¡qué nota! 🎵"
            else:
                prompt = "SISTEMA: El cliente envió VARIAS FOTOS para el video. Dile que están hermosas y pídele los detalles que falten para la letra."

            response = chat_sessions[conv_id].send_message(prompt)
            send_whatsapp(conv_id, response.text)
        except Exception as e:
            print(f"Error en lógica de imágenes: {e}")

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    
    # Chatwoot envía eventos, nosotros solo queremos 'message_created' que sean de clientes
    if data.get("event") == "message_created" and data.get("message_type") == "incoming":
        conv_id = data["conversation"]["id"]
        content = data.get("content", "")
        msg_attributes = data.get("attachments", [])
        
        # --- ESCUDO ANTI-SECUESTRO ---
        if conv_id in human_mode:
            if human_mode[conv_id] == True:
                reply_tranqui = "¡listo el pollo! 🍗 el equipo ya se pone en esas. dame de 12 a 24 horas y te traigo esa joya. ¡yo te aviso apenas quede lista! ✨"
                send_whatsapp(conv_id, reply_tranqui)
                human_mode[conv_id] = "AVISADO"
            return "OK", 200

        if conv_id not in chat_sessions:
            chat_sessions[conv_id] = client.chats.create(
                model=MODEL_ID,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.4,
                ),
            )

        # Lógica para Imágenes
        if msg_attributes and msg_attributes[0]["file_type"] == "image":
            if conv_id not in image_counts:
                image_counts[conv_id] = 1
                threading.Thread(target=handle_image_logic, args=(conv_id,)).start()
            else:
                image_counts[conv_id] += 1
            return "OK", 200

        # Lógica para Texto
        if content:
            user_text = content.lower()
            if any(x in user_text for x in ["pagué", "enviado", "comprobante", "listo el pago"]):
                human_mode[conv_id] = True
                reply = "¡recibido! 🚀 voy a pasarle esto al equipo. recuerda que en 12-24 horitas la tienes lista; yo misma te aviso apenas esté melo todo. ¡qué nota! 🎵"
                send_whatsapp(conv_id, reply)
            else:
                response = chat_sessions[conv_id].send_message(content)
                send_whatsapp(conv_id, response.text)
                
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
