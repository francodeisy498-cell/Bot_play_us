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
Eres "Aleja" 🇨🇴 de Play Us Music. Asesora de canciones personalizadas.
Tu estilo es: CONCRETO, ELEGANTE Y CÁLIDO. Hablas como una humana por WhatsApp.

CONFIDENCIALIDAD (REGLA ABSOLUTA):
- Jamás mencIONES que eres IA, bot o modelo de lenguaje.
- Jamás digas que las canciones se hacen con IA.
- Narrativa oficial: "Nuestro equipo de músicos y compositores se encarga de todo el proceso creativo". Somos un estudio de producción musical humana.

ESTILO DE ESCRITURA:
- Máximo 20-25 palabras por mensaje. Máximo 2 frases por mensaje.
- Sin párrafos largos, sin asteriscos, sin listas.
- Lenguaje natural de WhatsApp, elegante pero cercano.
- Trato principal: TÚ. Usa ocasionalmente "sumercé" o "veci" para dar cercanía, pero no en todos los mensajes.
- Expresiones permitidas: "Qué nota", "Claro que sí", "Qué maravilla", "Vea pues", "Imagínate", "De una".
- Expresiones prohibidas: "chimba", "parce", "mk", "gonorrea" o jerga vulgar.

FLUJO DE VENTA OBLIGATORIO:

1. RESPUESTA INICIAL (PRECIO):
Si preguntan qué haces o cuánto vale: "Tenemos la canción personalizada por 40 mil y la opción con video hecho con tus fotos por 70 mil. ¿Cuál prefieres?".

2. ELECCIÓN DEL CLIENTE:
Si el cliente elige 40 mil o 70 mil: "¡Excelente elección! Aquí tienes los medios de pago:".

3. MEDIOS DE PAGO (ENTREGAR COMPLETOS):
Nequi: 3117050514 (Angela Capera)
Daviplata: 3334005989 (Deivid Franco)
Bancolombia: 91240211764 (Alex Villamil)
Llave: @villamil982 (Alex Villamil)

4. RECOLECCIÓN E INFORMACIÓN FOTOS:
- Después de enviar los pagos, pide: "¿Para quién es la canción, qué género te gustaría y un poco de la historia?".
- SOLO si eligió el paquete de 70k, añade en el mismo mensaje: "También puedes enviarme las fotos o videos que te gustaría incluir para el video".

5. DUDA DE GÉNERO:
Sugiere algo breve: "Para algo romántico funciona muy bien acústico o balada. ¿Cuál te gusta más?".

6. RECEPCIÓN DE PAGO (1 IMAGEN):
Si envían comprobante: "¡Recibido! Muchas gracias. Ya envié el comprobante a producción para validar y comenzar tu canción. Va a quedar maravilloso.".

REGLA FINAL:
Responde siempre como asesora humana. Directa, cálida y elegante. No suenes robótica.
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

# --- FUNCIÓN DE ENVÍO (Soporta Notas Privadas) ---
def send_whatsapp(conv_id, text, is_private=False):
    url = f"{CHATWOOT_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/{conv_id}/messages"
    headers = { "api_access_token": CHATWOOT_ACCESS_TOKEN, "Content-Type": "application/json" }
    payload = { "content": text, "message_type": "outgoing", "private": is_private }
    try:
        requests.post(url, json=payload, headers=headers)
    except Exception as e:
        print(f"-> Error API Chatwoot: {e}")

# --- LÓGICA PARA IMÁGENES (Comprobante o Fotos Video) ---
def handle_image_logic(conv_id):
    time.sleep(35)
    if conv_id in image_counts:
        count = image_counts[conv_id]
        del image_counts[conv_id]
        try:
            if conv_id not in chat_sessions:
                chat_sessions[conv_id] = client.chats.create(model=MODEL_ID, config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION))
            
            if count == 1:
                # 1. Resumen Privado para ti
                res_priv = chat_sessions[conv_id].send_message("SISTEMA: El cliente mandó una foto de pago. Extrae el RESUMEN DE ORDEN (Paquete, Género, Dedica, Para, Historia) solo como datos.")
                send_whatsapp(conv_id, res_priv.text, is_private=True)
                
                # 2. Gracias público para el cliente
                res_pub = chat_sessions[conv_id].send_message("Agradece al cliente por el pago con mucha calidez y dile que ya enviaste todo al equipo.")
                send_whatsapp(conv_id, res_pub.text, is_private=False)
                
                human_mode[conv_id] = time.time()
            else:
                prompt = f"SISTEMA: El cliente envió {count} fotos para su video. Elógialas con cariño y pregunta si falta algún detalle de la historia."
                response = chat_sessions[conv_id].send_message(prompt)
                send_whatsapp(conv_id, response.text, is_private=False)
                
        except Exception as e:
            print(f"-> Error en handle_image_logic: {e}")

# --- LÓGICA PARA TEXTO ---
def process_gemini_message(conv_id, content):
    try:
        if conv_id not in chat_sessions:
            chat_sessions[conv_id] = client.chats.create(
                model=MODEL_ID, 
                config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION, temperature=0.6)
            )
        
        user_text = content.lower()
        confirmacion_pago = ["pagué", "pagado", "ya envie", "ya mande", "listo el pago", "comprobante", "transferí"]
        
        if any(x in user_text for x in confirmacion_pago):
            # 1. Resumen Privado
            extraction_prompt = "SISTEMA: El cliente pagó. Genera el RESUMEN DE ORDEN (Paquete, Género, Dedica, Para, Historia). No saludes."
            res_priv = chat_sessions[conv_id].send_message(extraction_prompt)
            send_whatsapp(conv_id, res_priv.text, is_private=True)
            
            # 2. Mensaje de Despedida Público
            thanks_prompt = "Agradece el pago de forma muy amable y natural (veci/sumercé). Dile que en un rato le confirmas todo."
            res_pub = chat_sessions[conv_id].send_message(thanks_prompt)
            send_whatsapp(conv_id, res_pub.text, is_private=False)
            
            human_mode[conv_id] = time.time()
        else:
            response = chat_sessions[conv_id].send_message(content)
            send_whatsapp(conv_id, response.text, is_private=False)

    except Exception as e:
        print(f"-> Error Crítico Gemini: {e}")

# --- RUTAS FLASK ---
@app.route("/", methods=["GET"])
def health_check():
    return "Servidor Aleja VIP Activo ✅", 200

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
