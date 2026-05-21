import requests

RISK_API_URL = "http://127.0.0.1:8000/predict"

def predict_risk(text):

    if not text or not text.strip():
        return {
            "risk_level": "UNKNOWN",
            "risk_score": 0.0
        }

    try:
        response = requests.post(
            RISK_API_URL,
            json={"text": text},
            timeout=5
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:
        print(f"[Risk API Error] {e}")

        return {
            "risk_level": "UNKNOWN",
            "risk_score": 0.0
        }