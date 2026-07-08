# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import io
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import List, Tuple

import fitz
from PIL import Image
from settings import settings
from vector_store import ChromaHybridStore
from vlm_client import get_vlm_client

logger = logging.getLogger(__name__)

test_docs = [
    """
    Billing FAQ: You can update payment method in Settings > Billing.
    Invoice generation occurs on the 1st of every month.
    If payment fails, your account is suspended after 7 days.
    Refunds are available within 14 days for unused balance.
    """,
    # Plan 1: Essential Connect
    """
    Essential Connect
    Price: $25.00/month.
    Includes:
    - 15 GB of high-speed 5G data;
    - Unlimited calls to all national networks;
    - Unlimited SMS;
    - Roaming - 2000 MB per month in EU/NA;
    - 5 GB Hotspot limit.
    """,
    # Plan 2: Apex Unlimited
    """
    Apex Unlimited
    Price: $65.00/month.
    Includes:
    - Truly Unlimited high-speed 15G data;
    - Unlimited calls to all national and 50+ international networks;
    - Unlimited SMS globally;
    - Unlimited calls to all national and 50+ international networks;
    - Unlimited SMS globally;
    - Roaming - 20000 MB per month globally;
    - Unlimited Hotspot (15GB at max speed);
    - Priority VIP Support.
    """,
    # Plan switching / upgrade / downgrade
    """
    Plan Switching Policy
    You can switch between plans at any time from Settings > Plan.
    Upgrades take effect immediately. You will be charged the prorated difference for the remaining days in the billing cycle.
    Downgrades take effect at the start of the next billing cycle. You will continue on your current plan until then.
    You can only switch plans once per billing cycle.
    To switch plans, go to Settings > Plan > Change Plan and select a new plan.
    """,
    # Cancellation
    """
    Cancellation Policy
    You can cancel your subscription at any time from Settings > Account > Cancel Subscription.
    Cancellation takes effect at the end of the current billing cycle. You will retain access to your plan until then.
    No partial refunds are issued for unused days after cancellation.
    If you cancel within 14 days of your first activation, you are eligible for a full refund (money-back guarantee).
    After cancellation, your data and account information are retained for 30 days before permanent deletion.
    """,
    # Early termination
    """
    Early Termination Policy
    If you are on a contract plan, early termination fees may apply.
    Early termination fee: $50 flat fee if cancelled before the contract end date.
    Month-to-month plans have no early termination fees.
    To check if you are on a contract plan, go to Settings > Plan > Contract Details.
    """,
    # Roaming details
    """
    Roaming Policy
    Essential Connect includes 2000 MB roaming per month in EU and North America.
    Apex Unlimited includes 20000 MB roaming per month globally.
    After roaming data is exhausted, you will be charged $0.01 per MB unless roaming is disabled.
    You can disable roaming at any time from Settings > Roaming to avoid overage charges.
    Roaming allowance resets on the 1st of every month along with your billing cycle.
    """,
    # Extra quota
    """
    Extra Data Quota
    You can purchase additional high-speed data quota at any time.
    Extra quota pricing: $10 per 5 GB block.
    Extra quota does not expire and carries over to the next billing cycle.
    To add extra quota, go to Settings > Data > Buy Extra Data, or ask the support agent.
    Extra quota applies on top of your plan allowance and is used after your plan data is exhausted.
    """,
    # Support escalation
    """
    Support and Escalation
    For billing disputes or unresolved issues, you can escalate to a support agent.
    Support tickets are typically resolved within 24-48 hours.
    Priority VIP Support (available on Apex Unlimited) guarantees a response within 2 hours.
    You can track your support ticket status in Settings > Support > My Tickets.
    """,
]

test_docs_metadata = {
    "Essential Connect": {
        "source": "plans",
        "type": "billing_details",
        "plan_name": "Essential Connect",
        "doc_scope": "plan_specific",
    },
    "Apex Unlimited": {
        "source": "plans",
        "type": "billing_details",
        "plan_name": "Apex Unlimited",
        "doc_scope": "plan_specific",
    },
    "Billing FAQ": {"source": "faq", "type": "policy", "topic": "billing", "doc_scope": "general"},
    "Plan Switching Policy": {"source": "faq", "type": "policy", "topic": "plan switching", "doc_scope": "general"},
    "Cancellation Policy": {"source": "faq", "type": "policy", "topic": "cancellation", "doc_scope": "general"},
    "Early Termination": {"source": "faq", "type": "policy", "topic": "early termination", "doc_scope": "general"},
    "Roaming Policy": {"source": "faq", "type": "policy", "topic": "roaming", "doc_scope": "general"},
    "Extra Data Quota": {"source": "faq", "type": "policy", "topic": "quota", "doc_scope": "general"},
    "Support and Escalation": {
        "source": "faq",
        "type": "policy",
        "topic": "support and escalation",
        "doc_scope": "general",
    },
    "Default": {"source": "faq", "type": "policy"},
}


def extract_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line.rstrip(".:")
    return "Default"


def build_default_docs():
    texts = test_docs
    metadatas = []
    for text in texts:
        title = extract_title(text)
        metadata = test_docs_metadata.get(title, {"source": "faq", "type": "policy"}).copy()
        metadata["title"] = title
        metadatas.append(metadata)
    return texts, metadatas


def clean_pdf_text(text: str) -> str:
    skip_patterns = [
        r"(?i)copyright\s+©",
        r"(?i)all rights reserved",
        r"(?i)confidential",
        r"(?i)proprietary",
        r"(?i)trade\s*mark",
        r"(?i)patent",
        r"(?i)legalinformation",
        r"(?i)disclaimer",
        r"(?i)without the prior written consent",
        r"(?i)intellectual property",
        r"(?i)as is",
        r"(?i)no warranty",
        r"(?i)liability",
        r"(?i)jurisdiction",
        r"(?i)governing law",
    ]

    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if len(line_stripped) < 3:
            continue

        skip_line = False
        for pattern in skip_patterns:
            if re.search(pattern, line_stripped):
                skip_line = True
                break

        if skip_line:
            continue

        cleaned_lines.append(line_stripped)

    return "\n".join(cleaned_lines)


def split_into_semantic_chunks(text: str, max_chunk_size: int = 800, overlap: int = 100) -> List[str]:

    troubleshooting_keywords = [
        "troubleshooting",
        "broadband indicator",
        "restore",
        "factory",
        "LED",
        "press the button",
    ]
    is_troubleshooting = any(kw.lower() in text.lower() for kw in troubleshooting_keywords)

    if is_troubleshooting and len(text) <= 1200:
        return [text]

    if len(text) <= max_chunk_size:
        return [text]

    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    current_chunk = []
    current_size = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_size = len(para)

        if current_size + para_size <= max_chunk_size:
            current_chunk.append(para)
            current_size += para_size
        else:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))

            if para_size > max_chunk_size:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                current_chunk = []
                current_size = 0
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    if current_size + len(sent) <= max_chunk_size:
                        current_chunk.append(sent)
                        current_size += len(sent)
                    else:
                        if current_chunk:
                            chunks.append(" ".join(current_chunk))
                        current_chunk = [sent]
                        current_size = len(sent)
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_size = 0
            else:
                current_chunk = [para]
                current_size = para_size

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


async def describe_image_with_vlm(image_bytes: bytes, filename: str, page_num: int, max_retries: int = 1) -> str:
    try:
        vlm = await get_vlm_client()
        return await vlm.describe_image(image_bytes, filename, page_num, max_retries=max_retries)
    except Exception as e:
        logger.error(f"Failed to describe image from {filename} page {page_num}: {e}")
        return f"[Image description failed on page {page_num + 1}]"


async def warmup_vlm():
    try:
        vlm = await get_vlm_client()
        import io

        from PIL import Image

        img = Image.new("RGB", (224, 224), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        dummy_image = buf.getvalue()
        await vlm.describe_image(dummy_image, "warmup.jpg", 0, max_tokens=10, max_retries=1)
        logger.info("VLM warmup completed successfully")
    except Exception as e:
        logger.warning(f"VLM warmup failed: {e}")


def extract_relevant_sections(text: str) -> str:
    lines = text.split("\n")
    relevant_lines = []

    section_indicators = [
        "led indicator",
        "status",
        "description",
        "front panel",
        "rear panel",
        "side panel",
        "button",
        "port",
        "interface",
        "connection",
        "troubleshooting",
        "hardware",
        "specification",
        "wi-fi",
        "wireless",
        "broadband",
        "internet",
        "wan",
        "lan",
        "usb",
        "phone",
        "reset",
        "power",
        "indicator",
        "flashing",
        "solid",
        "green",
        "off",
    ]

    skip_indicators = [
        "copyright",
        "trademark",
        "patent",
        "legal",
        "disclaimer",
        "confidential",
        "proprietary",
        "liability",
        "jurisdiction",
    ]

    for line in lines:
        line_lower = line.lower()

        should_skip = False
        for skip in skip_indicators:
            if skip in line_lower:
                should_skip = True
                break

        if should_skip:
            continue

        is_relevant = False
        for indicator in section_indicators:
            if indicator in line_lower:
                is_relevant = True
                break

        if is_relevant or len(line.strip()) > 20:
            relevant_lines.append(line)

    return "\n".join(relevant_lines)


async def process_pdf(pdf_path: Path) -> Tuple[List[str], List[dict]]:
    texts = []
    metadatas = []
    doc = fitz.open(pdf_path)
    filename = pdf_path.name

    logger.info(f"Processing PDF: {filename} ({len(doc)} pages)")

    for page_num, page in enumerate(doc):
        page_text = page.get_text("text").strip()
        cleaned_text = clean_pdf_text(page_text)

        if not cleaned_text:
            cleaned_text = ""

        relevant_text = extract_relevant_sections(cleaned_text)
        if not relevant_text:
            relevant_text = cleaned_text

        image_description = None
        try:
            pix = page.get_pixmap(dpi=200)
            page_image_bytes = pix.tobytes("png")

            img = Image.open(io.BytesIO(page_image_bytes))
            img.thumbnail((1024, 1024))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            small_image_bytes = buf.getvalue()

            image_description = await describe_image_with_vlm(small_image_bytes, filename, page_num, max_retries=1)
            if image_description and not image_description.startswith("[Image description failed"):
                logger.info(f"Page {page_num+1} visual description: {image_description[:100]}...")
            else:
                image_description = None
        except Exception as e:
            logger.warning(f"Failed to render/describe page {page_num + 1}: {e}")

        combined_text = relevant_text
        if image_description:
            combined_text += "\n\n--- Image Analysis ---\n" + image_description

        if combined_text.strip():
            chunks = split_into_semantic_chunks(combined_text, max_chunk_size=800, overlap=100)

            for chunk_idx, chunk in enumerate(chunks):
                texts.append(chunk)
                metadatas.append(
                    {
                        "source": "pdf",
                        "type": "document",
                        "filename": filename,
                        "page": page_num + 1,
                        "chunk": chunk_idx,
                        "total_chunks": len(chunks),
                        "doc_scope": "pdf_content",
                    }
                )

    doc.close()
    logger.info(f"Extracted {len(texts)} semantic chunks from {filename}")
    return texts, metadatas


async def main(pdf_path: str = None, force: bool = False, append: bool = False):
    if force and append:
        raise ValueError("Arguments --force-ingest and --append-ingest cannot be used together")

    if not settings.chroma_url:
        logger.warning("ChromaDB URL is not set. Skipping ingestion phase.")
        return

    if pdf_path:
        await warmup_vlm()

    if pdf_path:
        collection_name = settings.collection_troubleshooting
    else:
        collection_name = settings.collection_name

    store = ChromaHybridStore(collection_name=collection_name)
    existing_count = store.collection.count()

    all_texts = []
    all_metadatas = []

    # Default documents - only for billing collection (when no PDF)
    if not pdf_path:
        logger.info("Using default embedded test_docs for billing collection")
        texts, metadatas = build_default_docs()
        all_texts.extend(texts)
        all_metadatas.extend(metadatas)

    # Single PDF processing
    if pdf_path:
        pdf_file = Path(pdf_path)
        if pdf_file.exists() and pdf_file.suffix.lower() == ".pdf":
            logger.info(f"Processing PDF for troubleshooting collection: {pdf_file.name}")
            texts, metadatas = await process_pdf(pdf_file)
            all_texts.extend(texts)
            all_metadatas.extend(metadatas)
        else:
            logger.warning(f"PDF file not found or invalid: {pdf_path}")

    if not all_texts:
        logger.info("No documents to ingest. Skip.")
        return

    if existing_count > 0 and not force and not append:
        logger.info(f"ChromaDB already contains {existing_count} documents. Skip ingest.")
        return

    ids = [str(uuid.uuid4()) for _ in all_texts]
    await store.add_texts(all_texts, all_metadatas, ids, clear=force)

    if force:
        logger.info(
            f"ChromaDB collection {collection_name} was cleared and repopulated with {len(all_texts)} documents."
        )
    elif append:
        logger.info(f"{len(all_texts)} documents were appended to ChromaDB collection {collection_name}.")
    else:
        logger.info(f"ChromaDB collection {collection_name} is populated with {len(all_texts)} documents.")
