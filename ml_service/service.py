import io, os, re
from datetime import datetime
import numpy as np, tensorflow as tf, pytesseract, uvicorn
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException

pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

BASE = os.path.dirname(os.path.abspath(__file__))
type_model = tf.keras.models.load_model(os.path.join(BASE, "models", "invoice_classifier.keras"))
quality_model = tf.keras.models.load_model(os.path.join(BASE, "models", "quality_classifier.keras"))
TYPE_CLASSES = ["invoice", "other", "receipt"]
QUALITY_CLASSES = ["good", "poor"]

MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
DATE_PATTERNS = [
    rf"\b\d{{1,2}}[-/ .]{MONTH}[-/ .,]*\d{{2,4}}\b",
    rf"\b{MONTH}[ .]\d{{1,2}},? \d{{4}}\b",
    r"\b\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}\b",
    r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b",
]

def find_date(text):
    for line in text.splitlines():
        if re.search(r"date", line, re.I) and not re.match(r"\s*due", line, re.I):
            for p in DATE_PATTERNS:
                m = re.search(p, line, re.I)
                if m:
                    return m.group(0)
    return None

def find_supplier(text):
    for line in text.splitlines():
        l = re.sub(r"(commercial|tax)?\s*invoice", "", line, flags=re.I).strip()
        if len(re.findall(r"[A-Za-z]", l)) < 3: continue
        if re.match(r"\W*A\w{1,3}ress", l, re.I): continue
        if re.match(r"\d", l): continue
        if re.search(r",\s*[A-Z]{2}\s*\d{4,5}", l): continue
        if re.search(r"description|unit price|quantity|amount", l, re.I): continue
        if re.search(r"\bid\b|inv/|date|bill|#", l, re.I): continue
        name = re.split(r"\s*\W?\s*A\w{1,3}ress", l, flags=re.I)[0].strip()
        if len(name) >= 3:
            return name
    return None

def find_total(text):
    for line in reversed(text.splitlines()):
        if re.search(r"total|montant|amount|ttc", line, re.I):
            nums = re.findall(r"\d+[.,]\d{2}", line)
            if nums:
                return float(nums[-1].replace(",", "."))
    return None

def iso_date(s):
    if not s:
        return None
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s

def predict(model, classes, img):
    x = img.convert("RGB").resize((224, 224), Image.BILINEAR)
    x = np.expand_dims(np.array(x, dtype="float32"), 0)
    p = model.predict(x, verbose=0)[0]
    i = int(p.argmax())
    return classes[i], float(p[i])

app = FastAPI()

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        img = Image.open(io.BytesIO(await file.read()))
        img.load()
    except Exception:
        raise HTTPException(status_code=400, detail="Unsupported image format")

    dtype, dconf = predict(type_model, TYPE_CLASSES, img)
    qlabel, _ = predict(quality_model, QUALITY_CLASSES, img)

    warnings = []
    if qlabel == "poor":
        warnings.append("Image floue ou mal cadrée : reprendre la photo.")

    fields = {"supplier": None, "invoice_number": None, "invoice_date": None,
              "subtotal": None, "tax": None, "total": None}
    ocr_text = ""

    if dtype == "invoice":
        ocr_text = pytesseract.image_to_string(img.convert("L"), lang="eng")
        total = find_total(ocr_text)
        d = iso_date(find_date(ocr_text))
        fields.update({
            "supplier": find_supplier(ocr_text),
            "invoice_date": d if d and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else None,
            "total": f"{total:.2f}" if total is not None else None,
        })
    elif dtype == "receipt":
        warnings.append("Extraction des champs non prise en charge pour les tickets.")

    return {
        "mode": "real",
        "model_version": "mobilenetv2-v1",
        "classification": dtype,
        "confidence": round(dconf, 3),
        "quality": "acceptable" if qlabel == "good" else "retake_required",
        "warnings": warnings,
        "ocr_text": ocr_text,
        "fields": fields,
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)