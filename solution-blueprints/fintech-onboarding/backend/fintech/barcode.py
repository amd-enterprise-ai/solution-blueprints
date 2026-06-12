# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
from typing import Any

import cv2
import numpy as np
from pdf417decoder import PDF417Decoder
from PIL import Image as PILImage

logging.basicConfig(level=logging.INFO)
logger_docs_back_side = logging.getLogger("docs_back_side")


async def user_data_back_side(file) -> dict[str, Any]:
    logger_docs_back_side.info("=== Barcode extraction started (pdf417decoder) ===")

    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        logger_docs_back_side.error("Failed to decode image")
        return {"success": False, "reason": "invalid_image"}

    pil_img = PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    try:
        decoder = PDF417Decoder(pil_img)
        num_barcodes = decoder.decode()

        if num_barcodes <= 0:
            logger_docs_back_side.warning("No PDF417 barcode detected (decode returned 0)")
            return {"success": False, "reason": "barcode_not_detected"}

        logger_docs_back_side.info(f"PDF417 decoded successfully, found {num_barcodes} barcode(s)")

        raw_text = decoder.barcode_data_index_to_string(0).strip()
        logger_docs_back_side.info(f"Raw text extracted, length: {len(raw_text)} chars")

        preview_length = min(1000, len(raw_text))
        logger_docs_back_side.info(f"RAW BARCODE CONTENT (first {preview_length} chars):\n{raw_text[:preview_length]}")
        if len(raw_text) > 1000:
            logger_docs_back_side.info(f"... (total length: {len(raw_text)} chars)")

    except Exception as decode_err:
        logger_docs_back_side.exception(f"PDF417 decoding failed: {decode_err}")
        return {"success": False, "reason": "decode_error"}

    def parse_aamva_simple(raw: str) -> tuple[dict, dict]:
        fields = {}
        lines = raw.replace("\r", "\n").split("\n")

        for line in lines:
            line = line.strip()
            if not line or line.startswith("@") or line.startswith("ANSI "):
                continue

            if len(line) >= 3 and line[:3].isalpha() and line[:3].isupper():
                code = line[:3]
                value = line[3:].strip()
                fields[code] = value

        surname = fields.get("DCS", "").strip()
        first_name = fields.get("DAC", "").strip() or fields.get("DCT", "").strip()
        dob_raw = fields.get("DBB", "").strip()
        gender_code = fields.get("DBC", "").strip()

        date_of_birth = ""
        if len(dob_raw) == 8 and dob_raw.isdigit():
            month = dob_raw[0:2]
            day = dob_raw[2:4]
            year = dob_raw[4:8]
            date_of_birth = f"{year}-{month}-{day}"

        gender = ""
        if gender_code == "1":
            gender = "male"
        elif gender_code == "2":
            gender = "female"
        elif gender_code == "9":
            gender = "not_specified"

        normalized = {
            "name": first_name,
            "surname": surname,
            "dateOfBirth": date_of_birth,
            "gender": gender,
        }

        return normalized, fields

    try:
        normalized, raw_fields = parse_aamva_simple(raw_text)

        if not any(v for v in normalized.values() if v):
            logger_docs_back_side.warning("No meaningful fields extracted — check raw text format")
            return {
                "success": False,
                "reason": "no_valid_fields_extracted",
                "raw_text_preview": raw_text[:600] + "..." if len(raw_text) > 600 else raw_text,
            }

        logger_docs_back_side.info("AAMVA parsing successful")

        return {
            "success": True,
            "data": normalized,
            "raw_text_preview": raw_text[:600] + "..." if len(raw_text) > 600 else raw_text,
            "raw_fields": {k: v for k, v in raw_fields.items() if v},
        }

    except Exception as parse_err:
        logger_docs_back_side.exception(f"AAMVA parsing failed: {parse_err}")
        return {"success": False, "reason": "parse_error"}
