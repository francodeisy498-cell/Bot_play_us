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

MODEL_ID = "gemini-2.5-flash"

chat_sessions = {}
human_mode = {}
image_counts = {}

SYSTEM_INSTRUCTION = """
Eres "Aleja" 🇨🇴, vendes canciones personalizadas. Eres una mujer joven, amable y muy profesional.
Los pagos salen a nombre de Dei** Fra*** o Ale**** Vil*****.

ESTILO DE ESCRITURA (HUMANIZADO):
- Escribe como en WhatsApp: minúsculas, emojis naturales, "dale", "de una", "listo", "parce".
- VARIEDAD COLOMBIANA: "de una", "dale", "listo", "chévere", "bacano", "imagínate", "qué nota", "oiga".
- PROHIBIDO: No uses párrafos largos ni más de 30 palabras por mensaje.
- PROHIBIDO: No uses listas, ni asteriscos, ni guiones.

REGLAS DE ORO:
1. ADAPTACIÓN: Canción sola 40k, con video 70k. Pregunta siempre para quién es y qué género prefieren.
2. MEDIOS DE PAGO: Nequi/Daviplata: 3334005989 a nombre de Dei** Fra***, Bancolombia: 91240211764 a nombre de Ale**** Vil*****, Llave: @VILLAMIL982.
3. SI ENVÍA PAGO (1 FOTO): "¡recibido! 🚀 ya se lo pasé al equipo. en 12-24 horitas te aviso cuando esté lista. ¡qué nota! ✨"
4. FOTOS: Si envía varias fotos para el video, dile que están hermosas y pide detalles para la letra.
"""

def send_whatsapp(conv_id, text):
    url = f"{CHATWOOT_URL}/api/v1/accounts/{ACCOUNT_ID}/conversations/{conv_id}/messages"

    headers = {
        "api_access_token": CHATWOOT_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }

    payload = {
        "content": text,
        "message_type": "outgoing",
        "private": False
    }

    try:
        r = requests.post(url, json=payload, headers=headers)
        print(f"Enviado a Conv {conv_id}. Estado: {r.status_code}")
        print(r.text)
    except Exception as e:
        print(f"Error enviando a Chatwoot: {e}")


def handle_image_logic(conv_id):
    time.sleep(15)

    if conv_id in image_counts and conv_id not in human_mode:
        count = image_counts[conv_id]
        del image_counts[conv_id]

        try:

            if count == 1:
                human_mode[conv_id] = True
                prompt = "SISTEMA: El cliente envió 1 FOTO. Confirma que recibiste el pago y que en 12-24 horas estará lista."

            else:
                prompt = f"SISTEMA: El cliente envió {count} fotos. Dile que están hermosas y sigue con los detalles de la letra."

            response = chat_sessions[conv_id].send_message(prompt)

            send_whatsapp(conv_id, response.text)

        except Exception as e:
            print(f"Error en lógica de imágenes: {e}")


@app.route("/", methods=["GET"])
def health_check():
    return "bot activo", 200


@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json()

    print("WEBHOOK RECIBIDO")
    print(data)

    if data.get("event") == "message_created":

        # solo responder a mensajes entrantes
        if data.get("message_type") != "incoming":
            return "OK", 200

        conv_id = data["conversation"]["id"]

        content = data.get("content", "")
        attachments = data.get("attachments") or []

        # --- ESCUDO HUMANO ---
        if conv_id in human_mode:

            if human_mode[conv_id] == True:

                reply_tranqui = "¡listo el pollo! 🍗 el equipo ya se pone en esas. dame de 12 a 24 horas y yo misma te aviso apenas esté melo todo. ✨"

                send_whatsapp(conv_id, reply_tranqui)

                human_mode[conv_id] = "AVISADO"

            return "OK", 200

        # crear sesión gemini
        if conv_id not in chat_sessions:

            chat_sessions[conv_id] = client.chats.create(
                model=MODEL_ID,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.4,
                ),
            )

        # --- DETECCIÓN DE IMÁGENES ---
        if attachments:

            file_type = attachments[0].get("file_type", "")

            if "image" in file_type:

                if conv_id not in image_counts:

                    image_counts[conv_id] = 1

                    threading.Thread(
                        target=handle_image_logic,
                        args=(conv_id,)
                    ).start()

                else:

                    image_counts[conv_id] += 1

                return "OK", 200

        # --- LÓGICA DE TEXTO ---
        if content:

            user_text = content.lower()

            if any(x in user_text for x in ["pagué", "enviado", "comprobante"]):

                human_mode[conv_id] = True

                reply = "¡recibido! 🚀 ya se lo pasé al equipo. en 12-24 horitas te aviso apenas quede lista. ¡qué nota! ✨"

                send_whatsapp(conv_id, reply)

            else:

                try:

                    response = chat_sessions[conv_id].send_message(content)

                    send_whatsapp(conv_id, response.text)

                except Exception as e:

                    print(f"Error Gemini: {e}")

    return "OK", 200


if __name__ == "__main__":

    port = int(os.environ["PORT"])

    app.run(host="0.0.0.0", port=port)
