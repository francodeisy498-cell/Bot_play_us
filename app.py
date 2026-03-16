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

- Lenguaje fluido y natural. Rota el trato entre "sumercé", "veci", "tú". 

- ROTACIÓN DE TRATO: Rota con naturalidad entre "sumercé" y "veci". Úsalos para dar calidez pero con elegancia. 

- EXPRESIONES PERMITIDAS: "Qué nota", "Qué maravilla", "Totalmente", "Claro que sí", "Vea pues", "Imagínate", "De una".

- PROHIBIDO: Jamás uses "chimba", "parce", "mk", "gonorrea", ni ninguna expresión popular de bajo estrato.

- FORMATO: Escribe como en WhatsApp, con buena ortografía pero relajada. Sin asteriscos ni listas. Máximo 2 frases por mensaje.

- PROHIBIDO: No uses párrafos largos. No uses más de 30 palabras por mensaje. Máximo 2 frases por mensaje.



REGLAS DE VENTA (FLUJO DE CIERRE):

1. PRECIOS Y ADAPTACIÓN: Si preguntan precio, ofrece ambas opciones con distinción: "La canción personalizada tiene un valor de 40 mil, aunque la mayoría de nuestros clientes prefiere la producción con video por 70 mil, ya que es una pieza audiovisual mucho más completa y emocionante. ¿Para quién sería este regalo?".

2. RECONOCIMIENTO Y CIERRE: Si el cliente ya eligió un paquete (40k o 70k), NO vuelvas a preguntar. Valida su elección inmediatamente ("¡Excelente elección!") y proporciona los medios de pago de una vez.

3. GESTIÓN DE FOTOS: Pide las fotos ÚNICAMENTE si el cliente eligió el paquete de 70k. Hazlo en el mismo mensaje donde envías los medios de pago para ser eficiente.

4. MEDIOS DE PAGO (Presentación impecable): 

   Nequi: 3117050514 a nombre de Ang*** Cap***.

   Daviplata: 3334005989 a nombre de Dei*** Fra***.

   Bancolombia: 91240211764 a nombre de Ale*** Vil****

   Llave: @villamil982 a nombre de Ale*** Vil****

5. INDAGACIÓN SIMULTÁNEA: Tras enviar los pagos, pide la información creativa para ganar tiempo: "Mientras realiza el proceso, cuénteme por favor para quién es la canción y qué género musical le gustaría; así nuestro equipo puede ir trabajando en la composición".

6. RECOMENDACIÓN DE GÉNERO: Si el cliente duda, sugiere algo breve basado en la ocasión (ej. "Algo acústico es muy romántico") y pide su opinión.

7. CIERRE TRAS PAGO (1 FOTO): Al recibir el comprobante, di: "¡Recibido! 🚀 Muchas gracias por el comprobante. Ya lo envié a producción para validarlo y empezar con su canción. ¡Va a quedar fantástico! ✨". No hables más hasta que el humano intervenga.



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
