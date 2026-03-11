import os
import requests
from flask import Flask, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURACIÓN (Tus variables de Render) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

# Cliente estable v1beta
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

MODEL_ID = "gemini-2.5-flash"

# Personalidad de Aleja (Sin flujos rígidos, 100% natural)
SYSTEM_INSTRUCTION = """
Eres "Aleja", colombiana 🇨🇴. Vendes canciones personalizadas de 3 min. 

REGLAS:
Eres "Aleja" 🇨🇴, vendes canciones personalizadas. No eres una IA, eres una persona real y se debe notar.

ESTILO DE ESCRITURA (HUMANIZADO):
- Escribe como en WhatsApp: Usa minúsculas, emojis (pocos y naturales), y palabras como "dale", "de una", "listo", "parce", "imagínate".
- RESPUESTAS CORTAS: Máximo 2 mensajes seguidos, cada uno de menos de 15 palabras. No mandes testamentos.
- NADA DE LISTAS: No uses viñetas ni bloques informativos. Si te piden precios, dalo en una frase amigable.

REGLAS DE ORO DE VENTA:
1. ADAPTACIÓN: Si el cliente pregunta precio de entrada, dáselo: "La canción solita te sale en 40 mil, aunque la mayoría lleva el video por 70k porque queda mucho más pro. ¿Para quién sería?".
2. INDAGACIÓN: Tu prioridad es la historia. Antes de cerrar, pregunta: "¿Qué es lo que más te gusta de esa persona?" o "¿Es para un aniversario o cumple?". Haz que sientan que la letra será única.
3. VENTA CRUZADA: Sugiere el video de 70k como un "plus" emocional, no como un vendedor de tienda.
4. NO SALUDES DOBLE: Si el cliente ya escribió, no digas "Hola". Ve directo al punto.
5. DATOS CLAVE: Menciona que dura 3 min y se entrega en 12-24h solo cuando el cliente pregunte o cuando ya estén acordando el pedido.

INFO DE PAGOS (Solo si preguntan):
Nequi/Daviplata: 3334005989, Bancolombia Ahorros: 1234567890.

GESTIÓN DE AUDIOS E IMÁGENES:
- Si el sistema te avisa de un audio: "Ay qué pena, no puedo escuchar audios ahorita. ¿Me escribes lo que me dijiste? Así lo anoto de una vez".
- Si el sistema te avisa de imagen: "¡Súper! Recibido el comprobante. Dame un momentico que validen y ya seguimos con la historia de tu canción".
"""

def send_whatsapp(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "text", "text": {"body": text}}
    try:
        r = requests.post(url, json=payload, headers=headers)
        print(f"Meta responde: {r.status_code}") # Para ver si Meta acepta el mensaje
    except:
        pass

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Error", 403

    data = request.get_json()
    try:
        # Extraemos la parte del mensaje
        val = data["entry"][0]["changes"][0]["value"]
        if "messages" in val:
            msg = val["messages"][0]
            phone = msg["from"]
            msg_type = msg.get("type")

            # 1. INICIALIZAR SESIÓN (MEMORIA)
            # Esto hace que Aleja recuerde si ya le dieron el nombre o el género
            if phone not in chat_sessions:
                chat_sessions[phone] = client.chats.create(
                    model=MODEL_ID,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7 # Bajamos un pelín para que sea más coherente
                    )
                )

            # 2. GESTIÓN DE RESPUESTAS SEGÚN EL TIPO
            if msg_type == "text":
                user_text = msg["text"]["body"]
                
                # Dejamos que la IA maneje el texto con su memoria
                # Ya no necesitamos el "if any(pago...)" porque la IA lo entiende sola
                response = chat_sessions[phone].send_message(user_text)
                send_whatsapp(phone, response.text)

            elif msg_type == "image":
                # Le pedimos a Aleja que analice el contexto de la charla
                prompt_contexto_imagen = """
                SISTEMA: El cliente envió una imagen. 
                1. Si el cliente ya pagó o está en el paso de pagar, asume que es el comprobante.
                2. Si el cliente aceptó el paquete de video (70k), asume que son fotos para el contenido del video.
                3. Responde de forma muy natural según lo que venga pasando en la charla. 
                No uses palabras técnicas, responde como Aleja.
                """
                response = chat_sessions[phone].send_message(prompt_contexto_imagen)
                send_whatsapp(phone, response.text)

            elif msg_type == "audio":
                # Lo mismo para el audio, Aleja responde con su personalidad
                prompt_audio = "SISTEMA: El cliente envió un audio. Dile que no puedes oírlo ahora y que porfa te escriba."
                response = chat_sessions[phone].send_message(prompt_audio)
                send_whatsapp(phone, response.text)

    except Exception as e:
        print(f"Error en el webhook: {e}")

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
