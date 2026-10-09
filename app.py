import io
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from pypdf import PdfReader
from werkzeug.utils import secure_filename

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "docusahayak.db"
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_FILE_BYTES = 8 * 1024 * 1024
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_BYTES * 4

SCHEMES = {
    "scholarship": {
        "label": "Scholarship application preparation",
        "note": "Illustrative checklist only. Exact requirements depend on the scholarship and current official notice.",
        "documents": [
            "Previous examination marksheet",
            "Admission or bonafide certificate, if required",
            "Income certificate, if required",
            "Caste certificate, if applicable",
            "Identity proof, if required",
            "Bank account proof, if required"
        ],
        "source": "Verify requirements on the official scholarship portal or the latest scheme notification."
    },
    "income": {
        "label": "Income certificate preparation",
        "note": "Common preparation guidance only. Requirements vary by state, district and issuing authority.",
        "documents": [
            "Identity proof, if required",
            "Address or residence proof, if required",
            "Income-related supporting records, as requested",
            "Application form and declaration, if required"
        ],
        "source": "Check the official state service portal or local issuing authority for the current list."
    },
    "general": {
        "label": "General government application preparation",
        "note": "This is a general starting point, not an official scheme-specific checklist.",
        "documents": [
            "Application form for the selected service",
            "Identity proof, if required",
            "Address proof, if required",
            "Supporting certificates listed in the official instructions"
        ],
        "source": "Open the official service page and confirm the current checklist before applying."
    }
}


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS scheme_catalog (
            scheme_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            note TEXT NOT NULL,
            documents_json TEXT NOT NULL,
            source_note TEXT NOT NULL,
            last_reviewed TEXT NOT NULL
        )""")
        import json
        for scheme_id, scheme in SCHEMES.items():
            db.execute(
                "INSERT OR REPLACE INTO scheme_catalog VALUES (?, ?, ?, ?, ?, ?)",
                (scheme_id, scheme["label"], scheme["note"], json.dumps(scheme["documents"]), scheme["source"], "Prototype checklist; official source not independently verified")
            )


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text(file_storage, extension):
    """Extract text in memory. Uploaded files are never saved to disk."""
    raw = file_storage.read()
    file_storage.stream.seek(0)
    if not raw:
        return "", "The file is empty."
    if len(raw) > MAX_FILE_BYTES:
        return "", "Each file must be 8 MB or smaller."
    try:
        if extension == "pdf":
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if text.strip():
                return text[:30000], "Text extracted from PDF. Scanned-only PDFs may need local OCR."
            return "", "No selectable text found in this PDF. It may be scanned; image OCR needs Tesseract installed."
        from PIL import Image
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))
        try:
            import pytesseract
            text = pytesseract.image_to_string(image)
            if text.strip():
                return text[:30000], "Text extracted from image using local Tesseract OCR."
            return "", "OCR did not find readable text. Try a clearer, straight image."
        except (ImportError, Exception) as exc:
            # Keep uploaded data in memory; return a useful message if the OCR engine is not installed.
            return "", "Image received, but local OCR is unavailable. Install Tesseract OCR and pytesseract to read image text."
    except Exception:
        return "", "The file could not be read. Check that it is a valid PDF, JPG or PNG."


def normalize_name(value):
    value = value.lower().strip()
    value = re.sub(r"[^a-z\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_fields(text):
    """Conservative label-based extraction; does not claim to validate authenticity."""
    fields = {}
    if not text:
        return fields
    name_patterns = [
        r"(?:full\s*name|candidate\s*name|student\s*name|name)\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{1,70})",
    ]
    dob_patterns = [
        r"(?:date\s*of\s*birth|dob|birth\s*date)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})"
    ]
    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = re.split(r"\n|\b(?:father|mother|gender|dob|date of birth|address)\b", match.group(1), flags=re.IGNORECASE)[0].strip(" .:-")
            if 2 <= len(candidate) <= 70:
                fields["name"] = candidate
                break
    for pattern in dob_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            fields["dob"] = match.group(1).strip()
            break
    return fields


def compare_documents(documents):
    found = {"name": [], "dob": []}
    for document in documents:
        for field in found:
            if document.get("fields", {}).get(field):
                found[field].append({"document": document["name"], "value": document["fields"][field]})
    findings = []
    for field, entries in found.items():
        if len(entries) >= 2:
            normalized = {normalize_name(e["value"]) if field == "name" else re.sub(r"[^0-9]", "", e["value"]) for e in entries}
            if len(normalized) > 1:
                findings.append({
                    "severity": "review",
                    "title": f"Possible {field.upper()} mismatch",
                    "message": f"The extracted {field.upper()} differs across documents. Check the original documents carefully before applying.",
                    "evidence": entries
                })
            else:
                findings.append({
                    "severity": "ok",
                    "title": f"{field.upper()} appears consistent",
                    "message": f"The extracted {field.upper()} matches across the documents where it was found. This is not proof of document authenticity.",
                    "evidence": entries
                })
    if not findings:
        findings.append({
            "severity": "info",
            "title": "Manual verification needed",
            "message": "The system could not extract the same labelled field from at least two documents. Review the originals manually. OCR may miss fields or read them incorrectly.",
            "evidence": []
        })
    return findings


def local_assistant_reply(question, scheme_id="general"):
    q = question.lower()
    if any(word in q for word in ["hello", "hi", "नमस्कार", "नमस्ते"]):
        return "नमस्कार! मी document checklist, application preparation आणि संभाव्य चुका समजून घेण्यासाठी मदत करू शकतो. कोणत्या गोष्टीबद्दल मदत हवी आहे?"
    if any(word in q for word in ["scholarship", "शिष्यवृत्ती"]):
        return "Scholarship ची requirements scheme नुसार बदलतात. Marksheets, admission/bonafide proof, income certificate किंवा इतर कागदपत्रे लागू असू शकतात. आधी scheme ची अधिकृत, अद्ययावत checklist तपासा. येथे दाखवलेली checklist illustrative आहे."
    if any(word in q for word in ["name", "dob", "mismatch", "नाव", "जन्मतारीख", "चूक"]):
        return "नाव किंवा जन्मतारीख वेगळी दिसल्यास दोन्ही मूळ documents तपासा. OCR ची चूक असू शकते. स्वतःहून document बदलू नका. आवश्यक असल्यास संबंधित issuing authority च्या अधिकृत correction process बद्दल माहिती घ्या."
    if any(word in q for word in ["income", "उत्पन्न"]):
        return "Income certificate साठी लागणारी कागदपत्रे राज्य आणि issuing authority नुसार बदलू शकतात. Official state service portal किंवा स्थानिक authority कडील current checklist तपासा."
    if any(word in q for word in ["privacy", "security", "safe", "सुरक्षित"]):
        return "या prototype मध्ये uploaded files disk वर save केल्या जात नाहीत; त्या request process करताना memory मध्ये वाचल्या जातात. तरीही sensitive documents demo मध्ये upload करू नका. API वापरल्यास फक्त आवश्यक, कमी-संवेदनशील माहितीच पाठवावी."
    if any(word in q for word in ["document", "documents", "कागदपत्र"]):
        scheme = SCHEMES.get(scheme_id, SCHEMES["general"])
        return f"{scheme['label']} साठी checklist पहा. {scheme['note']} आवश्यक कागदपत्रे पूर्ण आहेत असे गृहीत धरू नका; official instructions शी तुलना करा."
    return "मी document preparation, checklist, नाव/DOB mismatch आणि privacy याबद्दल सामान्य मार्गदर्शन देऊ शकतो. नेमकी scheme सांगा. ही guidance आहे, अधिकृत निर्णय नाही."


def ask_gemini(question, scheme_id):
    if not GEMINI_API_KEY:
        return None
    scheme = SCHEMES.get(scheme_id, SCHEMES["general"])
    prompt = (
        "You are a cautious public-service document preparation assistant. Answer in simple Marathi or English matching the user's language. "
        "Do not claim to be a government official, do not invent scheme requirements, do not guarantee eligibility or approval. "
        "Tell the user to verify requirements on the official scheme portal. Do not ask for Aadhaar numbers or other sensitive identifiers. "
        f"Context: {scheme['label']}. Illustrative checklist: {', '.join(scheme['documents'])}. "
        f"Checklist note: {scheme['note']}\nUser question: {question[:1000]}"
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    try:
        response = requests.post(
            url,
            params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 350}},
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        return None


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/schemes")
def get_schemes():
    import json
    with get_db() as db:
        rows = db.execute("SELECT * FROM scheme_catalog ORDER BY scheme_id").fetchall()
    return jsonify({"schemes": [
        {"id": row["scheme_id"], "label": row["label"], "note": row["note"], "documents": json.loads(row["documents_json"]), "source_note": row["source_note"], "last_reviewed": row["last_reviewed"]}
        for row in rows
    ]})


@app.post("/api/check")
def check_documents():
    scheme_id = request.form.get("scheme_id", "general")
    if scheme_id not in SCHEMES:
        return jsonify({"error": "Select a valid checklist category."}), 400
    uploaded = request.files.getlist("documents")
    uploaded = [f for f in uploaded if f and f.filename]
    if not uploaded:
        return jsonify({"error": "Choose at least one PDF, JPG or PNG file."}), 400
    if len(uploaded) > 4:
        return jsonify({"error": "Upload a maximum of 4 documents at a time."}), 400
    documents = []
    errors = []
    for file in uploaded:
        safe_name = secure_filename(file.filename) or "uploaded-document"
        if not allowed_file(safe_name):
            errors.append(f"{safe_name}: unsupported file type.")
            continue
        text, note = extract_text(file, safe_name.rsplit(".", 1)[1].lower())
        documents.append({"name": safe_name, "text_found": bool(text.strip()), "text_preview": text[:500], "fields": extract_fields(text), "status": note})
    if not documents:
        return jsonify({"error": "No supported documents could be processed.", "details": errors}), 400
    findings = compare_documents(documents)
    return jsonify({
        "scheme": SCHEMES[scheme_id]["label"],
        "documents": [{"name": d["name"], "text_found": d["text_found"], "fields": d["fields"], "status": d["status"]} for d in documents],
        "findings": findings,
        "limitations": ["This checks extracted text only and cannot verify authenticity.", "A missing field may mean OCR could not read it, not that the document is invalid.", "The checklist is illustrative and must be checked against official current requirements."],
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "file_errors": errors
    })


@app.post("/api/demo")
def demo_report():
    sample_documents = [
        {"name": "sample_marksheet.txt (demo data)", "fields": {"name": "Aarav Patil", "dob": "12/04/2005"}},
        {"name": "sample_certificate.txt (demo data)", "fields": {"name": "Aarav P Patil", "dob": "12/04/2005"}},
    ]
    findings = compare_documents(sample_documents)
    return jsonify({
        "scheme": "Scholarship application preparation (sample report)",
        "documents": [{"name": d["name"], "text_found": True, "fields": d["fields"], "status": "Synthetic demo data; no real document uploaded."} for d in sample_documents],
        "findings": findings,
        "limitations": ["This is synthetic sample data, not a real document check.", "The name variation may be legitimate; verify the original records.", "This does not validate eligibility or authenticity."],
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "file_errors": []
    })


@app.post("/api/assistant")
def assistant():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    scheme_id = str(payload.get("scheme_id", "general"))
    if not question:
        return jsonify({"error": "Type a question first."}), 400
    if len(question) > 1000:
        return jsonify({"error": "Please keep the question under 1,000 characters."}), 400
    if scheme_id not in SCHEMES:
        scheme_id = "general"
    answer = ask_gemini(question, scheme_id)
    mode = "gemini" if answer else "local-guidance"
    if not answer:
        answer = local_assistant_reply(question, scheme_id)
    return jsonify({"answer": answer, "mode": mode, "notice": "Guidance only. Verify current requirements with the official scheme authority."})


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Upload too large. Keep each file under 8 MB and upload no more than 4 files."}), 413


@app.errorhandler(500)
def internal_error(_error):
    return jsonify({"error": "Something went wrong. Please try again with a supported sample file."}), 500


init_db()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
