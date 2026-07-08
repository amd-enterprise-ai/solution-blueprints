// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState } from "react";

interface RatingModalProps {
  roomName: string;
  userId?: string;
  onRatingSubmitted: () => void; // caller triggers END CALL after this
}

export function RatingModal({ roomName, userId, onRatingSubmitted }: RatingModalProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const labels: Record<number, string> = {
    1: "Very poor",
    2: "Poor",
    3: "Okay",
    4: "Good",
    5: "Excellent",
  };

  const handleSubmit = async () => {
    if (selected === null) return;
    setSubmitting(true);
    setError(null);

    try {
      const res = await fetch("/agent/session/rating", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          room_name: roomName,
          rating: selected,
          user_id: userId ?? null,
        }),
      });

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }

      onRatingSubmitted(); // triggers END CALL in parent
    } catch (e) {
      setError("Could not save your rating. Please try again.");
      setSubmitting(false);
    }
  };

  return (
      // Backdrop — not dismissible (no onClick on backdrop)
      <div className="rating-modal-backdrop">
        <div className="rating-modal">
          <h2 className="rating-modal__title">How was your experience?</h2>
          <p className="rating-modal__subtitle">
            Please rate the support you received today.
          </p>

          <div className="rating-modal__stars">
            {[1, 2, 3, 4, 5].map((star) => (
                <button
                    key={star}
                    className={`rating-modal__star ${selected === star ? "rating-modal__star--active" : ""} ${selected !== null && star <= selected ? "rating-modal__star--filled" : ""}`}
                    onClick={() => setSelected(star)}
                    disabled={submitting}
                    aria-label={labels[star]}
                    title={labels[star]}
                >
                  ★
                </button>
            ))}
          </div>

          {selected !== null && (
              <p className="rating-modal__label">{labels[selected]}</p>
          )}

          {error && <p className="rating-modal__error">{error}</p>}

          <button
              className="rating-modal__submit"
              onClick={handleSubmit}
              disabled={selected === null || submitting}
          >
            {submitting ? "Submitting…" : "Submit"}
          </button>
        </div>
      </div>
  );
}
