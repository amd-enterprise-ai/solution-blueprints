// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

export const AlertTriangle = ({ stroke = "#F04438" }: { stroke?: string }) => {
    return (
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M9.99988 7.50019V10.8335M9.99988 14.1669H10.0082M8.84598 3.24329L1.9919 15.0821C1.61173 15.7388 1.42165 16.0671 1.44974 16.3366C1.47425 16.5716 1.59739 16.7852 1.78852 16.9242C2.00765 17.0835 2.38704 17.0835 3.14581 17.0835H16.8539C17.6127 17.0835 17.9921 17.0835 18.2112 16.9242C18.4024 16.7852 18.5255 16.5716 18.55 16.3366C18.5781 16.0671 18.388 15.7388 18.0078 15.0821L11.1538 3.24329C10.775 2.58899 10.5856 2.26184 10.3385 2.15196C10.1229 2.05612 9.87684 2.05612 9.66129 2.15196C9.41419 2.26184 9.22478 2.58899 8.84598 3.24329Z" stroke={stroke} stroke-width="1.66667" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
    )
}
