<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# KYC Verification API Documentation

## Endpoints

### 1. Extract Face Embedding

**POST** `/extract_embedding`

Extracts a single face embedding from an uploaded photo.

**Request**
Content-Type: multipart/form-data
Body:

- file (UploadFile, required) — image containing a face (JPEG/PNG)

**Success Response** (200 OK)

```
{
  "success": true,
  "embedding": [
    0.123,
    -0.456,
    ...,
    0.789
  ],
  // 128 floats (normalized)
  "bbox": [
    x1,
    y1,
    x2,
    y2
  ],
  "det_score": 0.987,
  "age": 28,
  "gender": 1,
  "gender_str": "male"
}
```

**Error Response**
```
{
  "success": false,
  "reason": "no_face_detected" | "multiple_faces_detected" | "invalid_image"
}
```

### 2. Compare Two Face Embeddings

**POST** `/compare_faces`

Compares two 512-dimensional face embeddings using cosine similarity.

**Request**
Content-Type: application/json
Body:
```
{
  "live_embedding": [
    0.123,
    -0.456,
    ...
  ],
  // array of 512 floats
  "doc_embedding": [
    0.234,
    -0.567,
    ...
  ]
  // array of 512 floats
}
```

**Response** (200 OK)
```
{
  "match": true,
  "similarity": 0.6823,
  "threshold": 0.52,
  "note": "similarity ≥ threshold → considered a match"
}
```

Note: Fixed threshold 0.52 (configurable in code).

### 3. Liveness Check + Average Embedding

**POST** `/extract_live_embedding`

Performs liveness verification on a sequence of frames and returns averaged embedding if successful.

**Request**
Content-Type: multipart/form-data
Body:

- files (List[UploadFile], required) — multiple JPEG frames (~15–20 images, 10 seconds)

**Success Response** (200 OK)
```
{
  "success": true,
  "embedding": [
    0.123,
    -0.456,
    ...
  ],
  // averaged 512 floats
  "liveness_details": {
    "yaw_left_detected": true,
    "yaw_right_detected": true,
    "blink_detected": true,
    "final_state": 3,
    "challenge_passed": true
  }
}
```

**Error Response**
```
{
  "success": false,
  "reason": "challenge_not_passed" | "no_embeddings",
  "embedding": null,
  "liveness_details": {
    ...
  }
}
```

Liveness flow: yaw left → yaw right → blink.

### 4. Extract Data from Front Side (VLM + Embedding)

**POST** `/extract_user_data`

Parses text from driving license front side using VLM and extracts face embedding.

**Request**
Content-Type: multipart/form-data
Body:

- file (UploadFile, required) — photo of front side

**Success Response** (200 OK)
```
{
  "success": true,
  "embedding": [
    0.123,
    -0.456,
    ...
  ],
  "user_data": {
    "name": "John",
    "surname": "Doe",
    "gender": "male",
    "dateOfBirth": "1990-05-15"
  }
}
```

**Error Response**
```
{
  "success": false,
  "reason": "invalid_image" | "vlm_parse_error" |
  ...
}
```

### 5. Extract Data from Back Side (PDF417 Barcode)

**POST** `/extract_barcode_data`

Decodes PDF417 barcode from back side and parses AAMVA fields.

**Request**
Content-Type: multipart/form-data
Body:

- file (UploadFile, required) — photo of back side with barcode

**Success Response** (200 OK)
```
{
  "success": true,
  "data": {
    "name": "John",
    "surname": "Doe",
    "dateOfBirth": "1990-05-15",
    "gender": "male"
  },
  "raw_text_preview": "...",
  "raw_fields": {
    "DCS": "DOE",
    "DAC": "JOHN",
    "DBB": "05151990",
    ...
  }
}
```

**Error Response**
```
{
  "success": false,
  "reason": "invalid_image" | "barcode_not_detected" | "decode_error" | "no_valid_fields_extracted"
}
```

### 6. Health Check

**GET** /health

Simple health check endpoint.

**Response** (200 OK)
```
{
  "ok": true
}
```

## KYC Flow

1. Capture live video → send frames to /extract_live_embedding → get live embedding
2. Upload front side → /extract_user_data → get doc embedding + text data
3. Upload back side → /extract_barcode_data → get text data for verification
4. Compare embeddings → /compare_faces
5. Match text fields on frontend (name, surname, DOB, gender)
