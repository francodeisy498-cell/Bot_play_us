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

SYSTEM_INSTRUCTION = """
Eres "Aleja" 🇨🇴, representante de Play Us Music. Te diriges a un público distinguido. 
Tu tono es impecable, cálido, respetuoso y 100% humano. Eres una asesora de confianza.

REGLA DE ORO (CONFIDENCIALIDAD):
- PROHIBIDO: Jamás menciones que eres una IA, un bot o un modelo de lenguaje.
- PROHIBIDO: Jamás digas que las canciones son hechas por IA. 
- La narrativa es: "Nuestro equipo de músicos y compositores se encarga de todo el proceso creativo". Si preguntan, somos un estudio de producción humana.

ESTILO DE ESCRITURA (CERCANÍA RESPETUOSA):
- Usa un lenguaje pulido y afectuoso. 
- ROTACIÓN DE TRATO: Rota con naturalidad entre "sumercé" y "veci". Úsalos para dar calidez pero con elegancia.
- PALABRAS CLAVE: "Encantada", "Un gusto", "Claro que sí", "Excelente elección", "Qué detalle tan especial".
- PROHIBIDO: No uses "parce", "chimba", "bacano", "mk", ni expresiones vulgares o populares de barrio.
- FORMATO: Escritura clara, sin asteriscos ni listas. Máximo 2 frases por mensaje.
- PROHIBIDO: No uses párrafos largos. No uses más de 30 palabras por mensaje. Máximo 2 frases por mensaje.

REGLAS DE VENTA (EFICIENCIA Y CIERRE):
1. PRECIOS: La canción personalizada vale 40K y la opción con video profesional 70K.
2. Solo cuando el cliente elija el paquete de 70k, ahí sí pides las fotos
3. RECONOCIMIENTO: Si el cliente elige un paquete, NO preguntes de nuevo. Valida la elección y procede al pago de inmediato.
4. MEDIOS DE PAGO (Presentación clara): 
   Nequi: 3117050514 a nombre de Ang*** Cap***.
   Daviplata: 3334005989 a nombre de Dei*** Fra***.
   Bancolombia: 91240211764 a nombre de Ale*** Vil****
   Llave: @villamil982 a nombre de Ale*** Vil****
5. FLUJO: Una vez el cliente decida, proporciona los datos de pago y dile: "Mientras realiza el proceso, cuénteme por favor para quién es este regalo y qué género musical prefiere para que sea algo realmente único".
6. Si envían 1 foto (pago): "¡Recibido! 🚀 Muchas gracias por el comprobante veci. Ya lo he enviado al equipo para validarlo y comenzar con su canción. ¡Va a quedar fantástico! ✨".

REGLAS DE ORO DE VENTA:
1. ADAPTACIÓN: Si preguntan precio: "La canción solita te sale en 40 mil, aunque la mayoría lleva el video por 70k porque queda mucho más pro. ¿Para quién sería?".
2. INDAGACIÓN: Tu prioridad es la historia. Pregunta detalles para que la letra sea única. Y TAMBIÉN pregunta siempre qué género musical le gustaría.
3. RECOMENDACIÓN: Si te piden recomendación de género, responde algo corto y pide la opinión al usuario.
4. FOTOS: Si elige video, pide las fotos. Si las envía, dile que están hermosas.

REGLAS DE IMÁGENES:
- 1 foto: Es el comprobante. Agradece con distinción y activa modo humano.
- 2+ fotos: "¡Qué fotografías tan bonitas veci! 📸 Con este material el video tendrá un resultado increíble. Cuénteme un poco más sobre la historia que quiere transmitir sumercé...".
"""
# --- LIMPIEZA DE MEMORIA ---
def clean_memory():
    while True:
        time.sleep(3600)
        now = time.time()
        to_del_msg = [m for m, t in processed_messages.items() if now - t > 3600]
        for m in to_del_msg: del processed_messages[m]
        to_del_human = [c for c, t in human_mode.items() if isinstance(t, float) and now - t > 86400]
        for c in to_del_human: del human_mode[c]

threading.Thread(target=clean_memory, daemon=True).start()

def send_whatsapp(conv_id, text):
    url = f"{CHATWOOT_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/{conv_id}/messages"
    headers = { "api_access_token": CHATWOOT_ACCESS_TOKEN, "Content-Type": "application/json" }
    
    # Se envía el texto tal cual lo genera la IA (respetando mayúsculas naturales)
    payload = { "content": text, "message_type": "outgoing", "private": False }
    
    try:
        r = requests.post(url, json=payload, headers=headers)
        print(f"-> Chatwoot Status: {r.status_code}")
    except Exception as e:
        print(f"-> Error API Chatwoot: {e}")

# --- LÓGICA DE RESPUESTA ---

def handle_image_logic(conv_id):
    time.sleep(35) 
    if conv_id in image_counts:
        count = image_counts[conv_id]
        del image_counts[conv_id]
        try:
            prompt = "SISTEMA: El cliente envió 1 FOTO (pago)." if count == 1 else f"SISTEMA: El cliente envió {count} fotos para su video."
            if count == 1: human_mode[conv_id] = time.time()
            
            if conv_id not in chat_sessions:
                chat_sessions[conv_id] = client.chats.create(model=MODEL_ID, config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION))
            
            response = chat_sessions[conv_id].send_message(prompt)
            send_whatsapp(conv_id, response.text)
        except Exception as e:
            print(f"-> Error procesando imágenes: {e}")

def process_gemini_message(conv_id, content):
    try:
        if conv_id not in chat_sessions:
            chat_sessions[conv_id] = client.chats.create(
                model=MODEL_ID, 
                config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION, temperature=0.7)
            )
        
        user_text = content.lower()
        confirmacion_pago = ["pagué", "pagado", "ya envie", "ya mande", "listo el pago", "comprobante"]
        
        if any(x in user_text for x in confirmacion_pago):
            human_mode[conv_id] = time.time()
            reply = "¡Recibido! 🚀 Ya se lo pasé al equipo. En un ratico te confirmo todo. ¡Qué nota! ✨"
        else:
            response = chat_sessions[conv_id].send_message(content)
            reply = response.text
        
        send_whatsapp(conv_id, reply)
    except Exception as e:
        print(f"-> Error Crítico Gemini: {e}")

# --- RUTAS ---

@app.route("/", methods=["GET"])
def health_check():
    return "Servidor de Aleja Activo ✅", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    msg_id = str(data.get("id", ""))
    if msg_id and msg_id in processed_messages: return "OK", 200
    if msg_id: processed_messages[msg_id] = time.time()

    if data.get("message_type") != "incoming": return "OK", 200

    conv_id = data.get("conversation", {}).get("id") or data.get("message", {}).get("conversation_id")
    if not conv_id: return "OK", 200

    if conv_id in human_mode:
        t_pago = human_mode[conv_id]
        if isinstance(t_pago, float) and (time.time() - t_pago < 86400): return "OK", 200

    content = data.get("content") or ""
    attachments = data.get("attachments") or []

    if attachments and "image" in attachments[0].get("file_type", ""):
        image_counts[conv_id] = image_counts.get(conv_id, 0) + 1
        if image_counts[conv_id] == 1:
            threading.Thread(target=handle_image_logic, args=(conv_id,)).start()
    elif content:
        threading.Thread(target=process_gemini_message, args=(conv_id, content)).start()

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
