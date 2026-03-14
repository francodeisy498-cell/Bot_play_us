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

MODEL_ID = "gemini-2.5-flash" 

chat_sessions = {}
human_mode = {}
image_counts = {}
processed_messages = {}

# Tu System Instruction (Sin cambios)
SYSTEM_INSTRUCTION = """
Eres "Aleja" 🇨🇴, vendes canciones personalizadas. Eres una mujer joven, amable y muy profesional.
Los pagos se hacen a nombre de Deivid Franco.
ESTILO DE ESCRITURA: WhatsApp style, minúsculas, emojis naturales, "dale", "parce", "qué nota". Sin listas ni asteriscos.
REGLAS: Nequi/Daviplata: 3334005989 a nombre de Deivid Franco. 
Si envían 1 foto (pago): "¡recibido! 🚀 ya se lo pasé al equipo...". 
Si envían 2+ fotos: "¡ay qué nota! están hermosas...".
"""

def send_whatsapp(conv_id, text):
    url = f"{CHATWOOT_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/{conv_id}/messages"
    headers = { "api_access_token": CHATWOOT_ACCESS_TOKEN, "Content-Type": "application/json" }
    payload = { "content": text, "message_type": "outgoing", "private": False }
    try:
        r = requests.post(url, json=payload, headers=headers)
        print(f"-> Chatwoot Status: {r.status_code}")
    except Exception as e:
        print(f"-> Error: {e}")

def handle_image_logic(conv_id):
    time.sleep(30)
    if conv_id in image_counts and conv_id not in human_mode:
        count = image_counts[conv_id]
        del image_counts[conv_id]
        try:
            prompt = "SISTEMA: El cliente envió 1 FOTO (pago)." if count == 1 else f"SISTEMA: El cliente envió {count} fotos (video)."
            if count == 1: human_mode[conv_id] = True
            
            if conv_id not in chat_sessions:
                chat_sessions[conv_id] = client.chats.create(model=MODEL_ID, config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION))
            
            response = chat_sessions[conv_id].send_message(prompt)
            send_whatsapp(conv_id, response.text)
        except Exception as e:
            print(f"-> Error Imágenes: {e}")

def process_gemini_message(conv_id, content):
    try:
        if conv_id not in chat_sessions:
            chat_sessions[conv_id] = client.chats.create(model=MODEL_ID, config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION, temperature=0.4))
        
        user_text = content.lower()
        if any(x in user_text for x in ["pagué", "enviado", "comprobante", "pago"]):
            human_mode[conv_id] = True
            reply = "¡recibido! 🚀 ya se lo pasé al equipo. en 12-24 horitas te aviso cuando esté lista. ¡qué nota! ✨"
        else:
            response = chat_sessions[conv_id].send_message(content)
            reply = response.text
        
        send_whatsapp(conv_id, reply)
    except Exception as e:
        print(f"-> Error Gemini: {e}")

@app.route("/", methods=["GET"])
def health_check():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    
    # --- LOG DE DEPURACIÓN (Mira esto en Render) ---
    print(f"--- NUEVO MENSAJE RECIBIDO ---")
    print(f"Evento: {data.get('event')}, Tipo: {data.get('message_type')}")

    # 1. Filtro simplificado de duplicados
    msg_id = str(data.get("id", ""))
    if msg_id and msg_id in processed_messages:
        return "OK", 200
    if msg_id:
        processed_messages[msg_id] = time.time()

    # 2. Filtro de Mensajes (Solo entrantes)
    if data.get("message_type") != "incoming":
        return "OK", 200

    # 3. Extraer IDs (Con respaldo)
    conv_id = data.get("conversation", {}).get("id")
    if not conv_id and "message" in data:
        conv_id = data["message"].get("conversation_id")

    if not conv_id:
        print("-> No se pudo encontrar ID de conversación")
        return "OK", 200

    content = data.get("content") or ""
    attachments = data.get("attachments") or []

    # Escudo Humano
    if conv_id in human_mode:
        if human_mode[conv_id] == True:
            send_whatsapp(conv_id, "¡listo el pollo! 🍗 el equipo ya se pone en esas. dame un ratico.")
            human_mode[conv_id] = "AVISADO"
        return "OK", 200

    # Lógica de Imágenes
    if attachments:
        if "image" in attachments[0].get("file_type", ""):
            image_counts[conv_id] = image_counts.get(conv_id, 0) + 1
            if image_counts[conv_id] == 1:
                threading.Thread(target=handle_image_logic, args=(conv_id,)).start()
            return "OK", 200

    # Lógica de Texto
    if content:
        threading.Thread(target=process_gemini_message, args=(conv_id, content)).start()

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
