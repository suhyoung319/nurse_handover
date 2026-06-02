import os


RISK_API_URL = os.environ.get("RISK_API_URL", "http://127.0.0.1:8000/predict")


def predict_risk(text):
    if not text or not text.strip():
        return {
            "risk_level": "UNKNOWN",
            "risk_score": 0.0
        }

    try:
        import requests

        response = requests.post(
            RISK_API_URL,
            json={"text": text},
            timeout=5
        )

        response.raise_for_status()
        data = response.json()

        return {
            "risk_level": str(data.get("risk_level", "UNKNOWN")).upper(),
            "risk_score": float(data.get("confidence", data.get("risk_score", data.get("score", 0.0))) or 0.0),
        }

    except Exception as e:
        print(f"[Risk API Error] {e}")

        return {
            "risk_level": "UNKNOWN",
            "risk_score": 0.0
        }
