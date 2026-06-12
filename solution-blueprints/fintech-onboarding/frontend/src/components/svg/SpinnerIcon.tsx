// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

export default function SpinnerIcon({ size = 24, color = "white" }) {
  const segments = 8;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 21 22"
      xmlns="http://www.w3.org/2000/svg"
    >
      {Array.from({ length: segments }).map((_, i) => (
        <g key={i} transform={`rotate(${i * 45} 10.5 11)`}>
          <line
            x1="10.5"
            y1="2"
            x2="10.5"
            y2="5"
            stroke={color}
            strokeWidth="2"
            strokeLinecap="round"
          >
            <animate
              attributeName="y1"
              values="4;2;4"
              dur="1s"
              begin={`${i * 0.12}s`}
              repeatCount="indefinite"
            />
          </line>
        </g>
      ))}
    </svg>
  );
}
