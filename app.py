import os
import logging
import requests
import google.generativeai as genai
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Muat environment variables dari file .env
load_dotenv()

# Inisialisasi Flask app
app = Flask(__name__)

# Ambil API keys dari environment variables
FONTE_API_TOKEN = os.getenv("FONTE_API_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Validasi API keys
if not FONTE_API_TOKEN or not GEMINI_API_KEY:
    logging.error("API key untuk Fonnte atau Gemini tidak ditemukan. Harap set di file .env")
    logging.error("Anda bisa memilih untuk exit jika keys tidak ada")
    # exit()

# Konfigurasi Gemini API
try:
    genai.configure(api_key=GEMINI_API_KEY)

    # Konfigurasi model dengan system instruction
    # Ini adalah bagian paling penting untuk membatasi konteks chatbot
    SYSTEM_INSTRUCTION = (
        "Kamu adalah Theo, asisten virtual yang akan membantu menjawab pertanyaan seputar THT (Telinga, Hidung, dan Tenggorokan). "
        "Jawablah dengan ramah, singkat, dan profesional. "
        "Jika ada yang bertanya siapa Anda, perkenalkan diri Anda sebagai 'Theo', asisten yang siap membantu dengan informasi seputar THT. "
        "Berikan jawaban yang singkat, padat, dan jelas. Hindari respon yang terlalu panjang. "
        "Tugas utama Anda adalah memberikan informasi yang akurat dan umum terkait THT. "
        "PENTING: JANGAN memberikan diagnosis medis, resep, atau anjuran pengobatan spesifik. "
        "Selalu sarankan pengguna untuk berkonsultasi dengan dokter untuk masalah medis. "
        "Jika ada pertanyaan di luar konteks THT, tolak dengan sopan dan jelaskan bahwa Anda hanya dapat menjawab pertanyaan seputar THT."
    )

    model = genai.GenerativeModel(
        model_name='models/gemini-2.5-flash',
        system_instruction=SYSTEM_INSTRUCTION
    )
    logging.info("Model Gemini berhasil dikonfigurasi.")

except Exception as e:
    logging.error(f"Gagal mengkonfigurasi Gemini: {e}")
    model = None


def send_fonnte_reply(target: str, message: str):
    """ Fungsi untuk mengirim balasan melalui Fonnte API. """

    if not FONTE_API_TOKEN:
        logging.error("Fonnte API Token tidak ada, tidak bisa mengirim balasan.")
        return False

    headers = {
        'Authorization': FONTE_API_TOKEN,
    }

    payload = {
        'target': target,
        'message': message
    }

    try:
        response = requests.post('https://api.fonnte.com/send', headers=headers, data=payload)
        response.raise_for_status()  # Akan raise exception jika status code bukan 2xx
        logging.info(f"Berhasil mengirim balasan ke {target}: {response.json()}")
        return True

    except requests.exceptions.RequestException as e:
        logging.error(f"Gagal mengirim balasan via Fonnte: {e}")
        return False


@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    """ Endpoint untuk menerima pesan masuk dari Fonnte.
        Juga menangani GET request untuk verifikasi webhook.
    """

    if request.method == 'GET':
        # Fonnte (atau platform lain) terkadang mengirimkan GET untuk verifikasi
        logging.info("Menerima GET request ke webhook. Merespon dengan status OK.")
        return jsonify({"status": "success", "message": "Webhook is active and ready for POST requests."}), 200

    # Logika untuk POST request
    if request.method == 'POST':
        if not request.is_json:
            logging.warning("POST request tidak berisi JSON.")
            return jsonify({"status": "error", "message": "Request must be JSON"}), 400

        data = request.get_json()
        logging.info(f"Menerima data dari Fonnte: {data}")

        # Cek apakah ini pesan masuk atau hanya status update dari Fonnte
        user_message = data.get("message")
        if not user_message:
            logging.info("Menerima event status dari Fonnte, bukan pesan masuk. Mengabaikan.")
            return jsonify({"status": "ok", "message": "Status update received"}), 200

        # Ekstrak informasi dari payload Fonnte
        sender = data.get("sender")

        if not model:
            logging.error("Model Gemini tidak tersedia, tidak bisa memproses pesan.")
            send_fonnte_reply(sender, "Maaf, layanan chatbot sedang mengalami gangguan. Silakan coba lagi nanti.")
            return jsonify({"status": "error", "message": "Model not configured"}), 500

        try:
            # Kirim pesan ke Gemini
            logging.info(f"Mengirim pesan ke Gemini: {user_message}")
            response = model.generate_content(user_message)

            ai_reply = response.text
            logging.info(f"Menerima balasan dari Gemini: {ai_reply}")

            # Kirim balasan ke pengguna
            send_fonnte_reply(sender, ai_reply)

            return jsonify({"status": "success"}), 200

        except Exception as e:
            logging.error(f"Terjadi error saat memproses chat: {e}")
            send_fonnte_reply(sender, "Maaf, terjadi kesalahan saat memproses permintaan Anda.")
            return jsonify({"status": "error", "message": "Internal server error"}), 500

    # Fallback untuk metode lain yang tidak didukung
    return jsonify({"status": "error", "message": "Method not allowed"}), 405


@app.route('/')
def index():
    return "Backend Chatbot THT Aktif!"

if __name__ == '__main__':
    # Menjalankan aplikasi Flask. Port bisa disesuaikan.
    # Gunakan host='0.0.0.0' jika ingin diakses dari luar container/jaringan lokal.
    app.run(host='0.0.0.0', port=5000, debug=True)
