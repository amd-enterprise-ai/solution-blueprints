# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import json
import logging
import os
import uuid

from settings import settings
from vector_store import ChromaHybridStore

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
        title = extract_title(text=text)

        metadata = test_docs_metadata.get(title, {"source": "faq", "type": "policy"}).copy()

        metadata["title"] = title
        metadatas.append(metadata)

    return texts, metadatas


def load_custom_docs(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Custom data file not found: {path}")

    if not path.endswith(".json"):
        raise ValueError("Unsupported file format. Use .json")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("JSON file must contain a list of documents")

    texts = []
    metadatas = []

    for item in data:
        if isinstance(item, str):
            texts.append(item)
            metadatas.append({"source": "custom", "type": "generic"})
        elif isinstance(item, dict):
            text = item.get("text")
            if not text:
                raise ValueError("Each JSON object must contain a non-empty 'text' field")
            metadata = item.get("metadata", {"source": "custom", "type": "generic"})
            if not isinstance(metadata, dict):
                raise ValueError("'metadata' must be an object/dict")
            texts.append(text)
            metadatas.append(metadata)
        else:
            raise ValueError("Each item in JSON list must be either a string or an object")

    return texts, metadatas


async def main(custom_data_path=None, force=False, append=False):
    if force and append:
        raise ValueError("Arguments --force-ingest and --append-ingest cannot be used together")

    if not settings.chroma_url:
        logger.warning("ChromaDB URL is not set. Skipping ingestion phase.")
        return

    store = ChromaHybridStore()
    existing_count = store.collection.count()

    if custom_data_path:
        logger.info(f"Loading custom docs from: {custom_data_path}")
        texts, metadatas = load_custom_docs(custom_data_path)
    else:
        logger.info("Using default embedded test_docs")
        texts, metadatas = build_default_docs()

    if not texts:
        logger.info("No documents to ingest. Skip.")
        return

    if existing_count > 0 and not force and not append:
        logger.info(f"ChromaDB already contains {existing_count} documents. Skip ingest.")
        return

    ids = [str(uuid.uuid4()) for _ in texts]

    await store.add_texts(texts, metadatas, ids, clear=force)

    if force:
        logger.info(f"ChromaDB was cleared and repopulated with {len(texts)} documents.")
    elif append:
        logger.info(f"{len(texts)} documents were appended to ChromaDB.")
    else:
        logger.info(f"ChromaDB is populated with {len(texts)} documents.")
