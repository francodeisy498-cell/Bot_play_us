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

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

MODEL_ID = "gemini-2.5-flash"

chat_sessions = {}

SYSTEM_INSTRUCTION = """
Eres "Aleja" 🇨🇴, vendes canciones personalizadas de 3 minutos. Tu objetivo es cerrar la venta de forma humana, no robótica.

REGLAS DE ORO (COMPORTAMIENTO HUMANO):
1. ADAPTABILIDAD TOTAL: Si el cliente empieza preguntando el precio, dáselo de una. No le preguntes "cómo estás" ni le eches el discurso de bienvenida. 
2. NO REPITAS SALUDOS: Si ya te saludó o ya hablaron, prohibido decir "Hola" o "Soy Aleja". 
3. UN SOLO DATO A LA VEZ: Si el cliente está interesado, pide los datos de la letra (para quién, historia, género) uno por uno. Si el cliente dice "no sé" o "no", no insistas, dile: "Dale, yo me encargo de que quede hermosa con lo que me diste".
4. INFORMACIÓN CLAVE (Suéltala orgánicamente):
   - Precio: 40k audio / 70k con video.
   - Entrega: 12 a 24 horas.
   - Duración: 3 minutos aprox.
5. TONO: Colombiano relajado (usa: "dale", "de una", "claro que sí", "momentico"). Sin listas de precios tipo menú.

ESTADO DE PAGO:
Si el cliente envía un comprobante o dice que pagó, deja de vender. Solo confirma: "¡Listo! Ya lo mando a validar. Cuéntame los detalles para la letra mientras tanto".
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
        requests.post(url, json=payload, headers=headers)
    except:
        pass

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # ... (Parte del GET se mantiene igual) ...

    data = request.get_json()
    try:
        val = data["entry"][0]["changes"][0]["value"]
        if "messages" in val:
            msg = val["messages"][0]
            phone = msg["from"]
            msg_type = msg.get("type")

            # 1. Inicializar sesión si es nueva
            if phone not in chat_sessions:
                chat_sessions[phone] = client.chats.create(
                    model=MODEL_ID,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.8, # Un poco más de creatividad
                    )
                )

            # 2. Manejar Texto (Flujo Orgánico)
            if msg_type == "text":
                user_text = msg["text"]["body"]
                
                # Pequeño truco: si el cliente solo dice "Hola" y ya hay historia, 
                # le recordamos a la IA que no se presente.
                if len(chat_sessions[phone].history) > 1 and user_text.lower() in ["hola", "buenas", "buen día"]:
                    response = chat_sessions[phone].send_message("SISTEMA: El cliente saludó de nuevo. No te presentes, solo sigue la charla donde quedó.")
                else:
                    response = chat_sessions[phone].send_message(user_text)
                
                send_whatsapp(phone, response.text)

            # 3. Manejar Imágenes (Comprobantes)
            elif msg_type == "image":
                # Le avisamos a la IA internamente que llegó una imagen
                chat_sessions[phone].send_message("SISTEMA: El cliente envió una imagen (probablemente un comprobante). Confirma recibido y pide datos si faltan.")
                confirmacion = "¡Súper! Recibido el comprobante. Dame un momentico que validen el pago y ya seguimos con los detalles de tu canción. 🎵"
                send_whatsapp(phone, confirmacion)

            # 4. Manejar Audios (Para que no se quede callada)
            elif msg_type == "audio":
                aviso_audio = "¡Ay qué pena contigo! No alcancé a escucharte bien porque estoy en la calle. ¿Me podrías escribir lo que me dijiste? Así lo anoto de una vez."
                send_whatsapp(phone, aviso_audio)

    except Exception as e:
        print(f"Error: {e}")

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
