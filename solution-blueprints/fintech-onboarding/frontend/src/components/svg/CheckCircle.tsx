// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

export const CheckCircle = ({ stroke }: { stroke?: string }) => {
    return (
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
            <g clip-path="url(#clip0_9413_640)">
            <path d="M6.25008 9.99984L8.75008 12.4998L13.7501 7.49984M18.3334 9.99984C18.3334 14.6022 14.6025 18.3332 10.0001 18.3332C5.39771 18.3332 1.66675 14.6022 1.66675 9.99984C1.66675 5.39746 5.39771 1.6665 10.0001 1.6665C14.6025 1.6665 18.3334 5.39746 18.3334 9.99984Z" stroke={stroke ?? "#17B26A"} stroke-width="1.66667" stroke-linecap="round" stroke-linejoin="round"/>
            </g>
            <defs>
            <clipPath id="clip0_9413_640">
            <rect width="20" height="20" fill="white"/>
            </clipPath>
            </defs>
        </svg>

    )
}
