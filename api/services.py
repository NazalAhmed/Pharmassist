import re

import cv2
import numpy as np
import pytesseract
from pytesseract import Output
from PIL import Image
from rapidfuzz import process, fuzz

from .models import Medicine, Prescription, PrescriptionMedicine, Patient

import secrets
from django.utils import timezone
from datetime import timedelta

# ============================================================
# 0. Image preprocessing (deskew, denoise, upscale)
# ============================================================

def deskew_image(image_path):
    """
    Correct rotation so text lines are roughly horizontal.
    Returns a cv2 (numpy) image, not a PIL image.
    """

    image = cv2.imread(image_path)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)

    thresh = cv2.threshold(
        gray, 0, 255,
        cv2.THRESH_BINARY | cv2.THRESH_OTSU
    )[1]

    coords = np.column_stack(np.where(thresh > 0))

    if coords.shape[0] == 0:
        return image  # nothing to deskew against - bail out safely

    angle = cv2.minAreaRect(coords)[-1]

    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    # Don't attempt huge "corrections" - usually means detection was noise
    if abs(angle) > 15:
        return image

    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)

    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    rotated = cv2.warpAffine(
        image, matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )

    return rotated


def preprocess_for_ocr(image_path):
    """
    Deskew -> grayscale -> upscale -> denoise -> adaptive threshold.
    Returns a numpy array (single-channel) ready for pytesseract.
    """

    deskewed = deskew_image(image_path)

    gray = cv2.cvtColor(deskewed, cv2.COLOR_BGR2GRAY)

    # Upscale - small print reads much better to Tesseract at 2x
    gray = cv2.resize(
        gray, None,
        fx=2, fy=2,
        interpolation=cv2.INTER_CUBIC
    )

    gray = cv2.fastNlMeansDenoising(gray, h=30)

    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 11
    )

    return thresh


_HEADER_KEYWORDS = re.compile(
    r"\b(hospital|clinic|doctor|dr\.?|address|phone|email|date|age|name|"
    r"diagnosis|op\s*number|booking|review|remarks|signature|mbbs|md|dm|"
    r"prescription|rx)\b",
    re.IGNORECASE
)


_DOSAGE_FORM_WORDS = {
    "tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules",
    "syrup", "susp", "suspension", "inj", "injection", "drop", "drops",
    "cream", "lotion", "gel", "spray", "rotacaps", "rotacap", "sachet",
    "oint", "ointment", "mg", "mcg", "ml", "gm", "iu",
}


def clean_medicine_name(name):

    name = name.strip()

    name = re.sub(r"^[^A-Za-z0-9]+", "", name)

    # Remove frequency-looking tokens (e.g. "0-0-1")
    name = re.sub(r"\b[0-9/]+(?:\s*-\s*[0-9/]+){1,2}\b", "", name)

    name = re.sub(r"[*_~]+", " ", name)

    name = re.sub(r"\s+[A-Z]?\d{2,5}$", "", name)

    # Drop generic dosage-form/unit words, but keep numbers/strengths
    # (e.g. "50/500") and SR/OD/XR/DSR, which are real brand distinctions
    words = name.split()
    words = [w for w in words if w.lower().strip(".,") not in _DOSAGE_FORM_WORDS]
    name = " ".join(words)

    name = re.sub(r"\s+", " ", name)

    return name.strip()

def extract_medicine_lines_loose(text):
    """
    Fallback used when the strict numbered-list parser finds nothing -
    common on noisy/skewed OCR. Treats any line that doesn't look like
    header/footer text as a possible medicine line, so we always
    surface *something* for the pharmacist to review rather than
    an empty result.
    """

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    candidates = []

    for line in lines:

        cleaned = re.sub(r"^[^A-Za-z0-9]+", "", line).strip()

        if len(cleaned) < 3:
            continue

        if _HEADER_KEYWORDS.search(cleaned):
            continue

        letters = sum(c.isalpha() for c in cleaned)

        if letters < 3:
            continue

        candidates.append({
            "number": None,
            "medicine_name": cleaned,
            "generic_name": "",
            "frequency": "",
            "duration": "",
            "raw_text": line,
        })

    return candidates


# ============================================================
# 1. OCR
# ============================================================

def extract_text_from_image(image_path):
    """
    Convert prescription image into raw text using Tesseract,
    after deskewing/denoising/upscaling.
    """

    processed = preprocess_for_ocr(image_path)
    pil_image = Image.fromarray(processed)

    text = pytesseract.image_to_string(
        pil_image,
        lang="eng",
        config="--oem 3 --psm 6"
    )

    return text

# ============================================================
# 2b. Header field extraction
# ============================================================

def extract_header_fields(text):
    """
    Best-effort extraction of the prescription's header info.
    Every field defaults to "" if not found - OCR noise on this
    kind of letterhead means some fields will come back empty or
    slightly garbled; that's expected with Tesseract on this layout.
    """

    fields = {
        "doctor_name": "",
        "hospital_name": "",
        "op_number": "",
        "prescription_date": "",
        "patient_name": "",
        "age": "",
        "address": "",
        "diagnosis": "",
    }

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Hospital name: first line near the top mentioning "HOSPITAL"
    for line in lines[:8]:
        if "hospital" in line.lower():
            fields["hospital_name"] = line
            break

    # Doctor: a line starting with "Dr" - grab the whole line since
    # qualifications (MD, DM, MBBS...) usually follow on the same line
    for line in lines[:10]:
        if re.match(r"^Dr\.?\s", line, re.IGNORECASE):
            fields["doctor_name"] = line
            break

    def find_field(label_pattern):
        match = re.search(
            label_pattern + r"\s*:?\s*(.+)",
            text,
            re.IGNORECASE
        )
        return match.group(1).strip() if match else ""

    fields["op_number"] = find_field(r"OP\s*Number")
    fields["prescription_date"] = find_field(r"(?<!OP )\bDate\b")
    fields["patient_name"] = find_field(r"\bName\b")
    fields["age"] = find_field(r"\bAge\b")
    fields["address"] = find_field(r"\bAddress\b")
    fields["diagnosis"] = find_field(r"DIAGNOSIS")

    # Each of these can accidentally swallow the next label on the
    # same OCR line (e.g. "Name: X Age: 65") - cut it off there.
    stop_words = r"\b(?:Age|Gender|Sex|Date|DOB|Address|Name|Phone|Email|Diagnosis)\b"

    for key in ["op_number", "prescription_date", "patient_name", "age", "address", "diagnosis"]:
        value = fields[key]
        value = re.split(stop_words, value, flags=re.IGNORECASE)[0]
        fields[key] = value.strip(" :\n-")

    return fields

# ============================================================
# 2c. Table-aware medicine extraction (position-based)
# ============================================================

def extract_table_medicines(image_path):
    """
    Uses word bounding boxes (not flat text) to reconstruct the
    medicine table by column. Far more reliable than regex on
    flattened OCR text for tabular layouts like Dosage/Day/Qty.

    Returns None if the table header ("Dosage", "Day", "Qty")
    can't be located, so the caller can fall back to line-based
    extraction on plain text.
    """

    processed = preprocess_for_ocr(image_path)
    pil_image = Image.fromarray(processed)

    data = pytesseract.image_to_data(
        pil_image,
        lang="eng",
        config="--oem 3 --psm 6",
        output_type=Output.DICT
    )

    words = []

    for i in range(len(data["text"])):

        text = data["text"][i].strip()

        if not text:
            continue

        words.append({
            "text": text,
            "left": data["left"][i],
            "top": data["top"][i],
        })

    if not words:
        return None

    # --------------------------------------------------------
    # Locate the header row to determine column boundaries
    # --------------------------------------------------------

    column_x = {}

    for word in words:
        key = word["text"].lower().strip(":")
        if key in ("dosage", "day", "qty") and key not in column_x:
            column_x[key] = word["left"]

    if not all(k in column_x for k in ("dosage", "day", "qty")):
        return None  # couldn't find the header - caller should fall back

    dosage_x = column_x["dosage"]
    day_x = column_x["day"]
    qty_x = column_x["qty"]

    # --------------------------------------------------------
    # Group words into rows by vertical position
    # --------------------------------------------------------

    rows_by_bucket = {}

    for word in words:
        bucket = word["top"] // 15  # tolerate a few px of jitter per line
        rows_by_bucket.setdefault(bucket, []).append(word)

    table_rows = []

    for bucket in sorted(rows_by_bucket.keys()):

        line_words = sorted(rows_by_bucket[bucket], key=lambda w: w["left"])

        line_text_lower = " ".join(w["text"].lower() for w in line_words)

        if "dosage" in line_text_lower and "qty" in line_text_lower:
            continue  # skip the header row itself

        brand_words, dosage_words, day_words, qty_words = [], [], [], []

        for word in line_words:
            x = word["left"]

            if x < dosage_x - 10:
                brand_words.append(word["text"])
            elif x < day_x - 10:
                dosage_words.append(word["text"])
            elif x < qty_x - 10:
                day_words.append(word["text"])
            else:
                qty_words.append(word["text"])

        brand_text = " ".join(brand_words).strip()

        if not brand_text:
            continue

        table_rows.append({
            "raw_left_text": brand_text,
            "dosage": " ".join(dosage_words).strip(),
            "day": " ".join(day_words).strip(),
            "qty": " ".join(qty_words).strip(),
        })

    return table_rows if table_rows else None


def group_table_rows_into_medicines(rows):
    """
    Merges a numbered brand-name row with its following
    generic-name-in-parens row into one medicine entry.
    """

    medicines = []
    current = None

    for row in rows:

        left_text = row["raw_left_text"]
        has_details = bool(row["dosage"] or row["day"] or row["qty"])

        match = re.match(r"^(\d{1,2})[\.\)]?\s*(.+)$", left_text)

        if match and has_details:

            if current:
                medicines.append(current)

            current = {
                "medicine_name": match.group(2).strip(),
                "generic_name": "",
                "frequency": row["dosage"],
                "duration": row["day"],
                "quantity": row["qty"],
            }

        elif current and left_text.startswith("("):
            current["generic_name"] = left_text.strip("() ")

        elif current and not has_details:
            current["generic_name"] = (current["generic_name"] + " " + left_text).strip()

    if current:
        medicines.append(current)

    if not medicines:
        medicines = extract_medicine_lines_loose(text)

    return medicines


def match_medicine(ocr_name, ocr_generic_name=""):
    """
    Match OCR medicine name against the Medicine database.
    Always returns the closest match found, even at low confidence -
    never rejects outright. confidence_score tells the pharmacist
    how much to trust it; the decision to use it is theirs.
    """

    ocr_name_clean = clean_medicine_name(ocr_name)

    medicines = list(Medicine.objects.all())

    if not medicines:
        return None, 0

    # --- Exact brand match ---
    for medicine in medicines:
        if medicine.medicine_name.lower() == ocr_name_clean.lower():
            return medicine, 100

    # --- Fuzzy brand match ---
    brand_names = [m.medicine_name for m in medicines]

    brand_result = process.extractOne(
        ocr_name_clean, brand_names, scorer=fuzz.token_sort_ratio
    )

    best_medicine, best_score = None, 0

    if brand_result:
        _, score, idx = brand_result
        best_medicine, best_score = medicines[idx], score

    # --- Fuzzy generic-name fallback, tried if brand match is weak ---
    if ocr_generic_name and best_score < 80:

        generic_clean = clean_medicine_name(ocr_generic_name)

        candidates = [
            (i, m.generic_name) for i, m in enumerate(medicines) if m.generic_name
        ]

        if candidates:
            names_only = [c[1] for c in candidates]

            generic_result = process.extractOne(
                generic_clean, names_only, scorer=fuzz.token_sort_ratio
            )

            if generic_result:
                _, gen_score, gen_idx = generic_result

                if gen_score > best_score:
                    real_idx = candidates[gen_idx][0]
                    best_medicine, best_score = medicines[real_idx], gen_score

    # No threshold cutoff - the closest guess is returned regardless of
    # score. A low score is a signal for the pharmacist, not a reason
    # to drop the line entirely.
    return best_medicine, best_score

# ============================================================
# 6. Complete prescription processing
# ============================================================

def process_prescription_text(text, image_path=None):

    medicine_blocks = None

    if image_path:
        try:
            table_rows = extract_table_medicines(image_path)
            if table_rows:
                medicine_blocks = group_table_rows_into_medicines(table_rows)
        except Exception as e:
            print(f"Table extraction failed, falling back to text parsing: {e}")
            medicine_blocks = None

    if not medicine_blocks:
        medicine_blocks = extract_medicine_blocks(text)

    results = []

    for item in medicine_blocks:

        medicine, confidence = match_medicine(
            item["medicine_name"],
            item.get("generic_name", "")
        )

        if confidence >= 85:
            match_quality = "high"
        elif confidence >= 60:
            match_quality = "medium"
        else:
            match_quality = "low"

        results.append({
            "extracted_name": item["medicine_name"],
            "generic_name": item.get("generic_name", ""),
            "dosage": item.get("dosage", ""),
            "frequency": item.get("frequency", ""),
            "duration": item.get("duration", ""),
            "quantity": item.get("quantity", ""),
            "confidence_score": confidence,
            "match_quality": match_quality,
            "matched_medicine": medicine.medicine_name if medicine else None,
            "available": medicine.available if medicine else None,
            "alternatives": get_alternatives(medicine) if medicine and not medicine.available else [],
        })

    return results

# ============================================================
# 7. Full prescription processing (OCR -> match -> save)
# ============================================================

def process_prescription_full(prescription):

    prescription.status = "processing"
    prescription.save()

    try:
        image_path = prescription.prescription_file.path
    except Exception as e:
        prescription.status = "failed"
        prescription.save()
        print(f"Prescription {prescription.id}: couldn't access file - {e}")
        return prescription

    # OCR is the one truly essential step - without text, there's
    # nothing to work with.
    try:
        text = extract_text_from_image(image_path)
    except Exception as e:
        prescription.status = "failed"
        prescription.save()
        print(f"Prescription {prescription.id}: OCR failed - {e}")
        return prescription

    prescription.extracted_text = text

    # Header fields - best-effort, never fatal
    try:
        header = extract_header_fields(text)
    except Exception as e:
        print(f"Prescription {prescription.id}: header extraction failed - {e}")
        header = {k: "" for k in [
            "doctor_name", "hospital_name", "op_number",
            "prescription_date", "patient_name", "age", "address", "diagnosis"
        ]}

    prescription.doctor_name = header["doctor_name"]
    prescription.hospital_name = header["hospital_name"]
    prescription.op_number = header["op_number"]
    prescription.prescription_date = header["prescription_date"]
    prescription.diagnosis = header["diagnosis"]

    if header["patient_name"] and not prescription.patient.name:
        prescription.patient.name = header["patient_name"]
    if header["age"]:
        prescription.patient.age = header["age"]
    if header["address"]:
        prescription.patient.address = header["address"]

    prescription.patient.save()

    # Medicine extraction + matching - best-effort, never fatal.
    # Table-based extraction failures already fall back inside
    # process_prescription_text(); this is a second safety net.
    try:
        medicines = process_prescription_text(text, image_path=image_path)
    except Exception as e:
        print(f"Prescription {prescription.id}: extraction failed, retrying without image - {e}")
        try:
            medicines = process_prescription_text(text, image_path=None)
        except Exception as e2:
            print(f"Prescription {prescription.id}: fallback extraction also failed - {e2}")
            medicines = []

    prescription.medicines.all().delete()

    for item in medicines:

        matched_medicine = None

        if item["matched_medicine"]:
            try:
                matched_medicine = Medicine.objects.get(medicine_name=item["matched_medicine"])
            except Medicine.DoesNotExist:
                matched_medicine = None

        PrescriptionMedicine.objects.create(
            prescription=prescription,
            medicine=matched_medicine,
            extracted_name=item["extracted_name"],
            dosage=item["dosage"],
            frequency=item["frequency"],
            duration=item["duration"],
            quantity=item["quantity"],
            confidence_score=item["confidence_score"],
            pharmacist_verified=False,
        )

    # Completed as long as OCR itself succeeded - even a short or
    # low-confidence medicine list is a valid result, not a failure.
    prescription.status = "completed"
    prescription.save()

    return prescription