// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";

import { cn } from "@/libs/utils";
import styles from "./Button.module.scss";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
  size?: "default" | "sm" | "lg" | "icon";
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";

    const variantClass =
      variant === "destructive"
        ? styles.variantDestructive
        : variant === "outline"
          ? styles.variantOutline
          : variant === "secondary"
            ? styles.variantSecondary
            : variant === "ghost"
              ? styles.variantGhost
              : variant === "link"
                ? styles.variantLink
                : styles.variantDefault;

    const sizeClass =
      size === "sm"
        ? styles.sizeSm
        : size === "lg"
          ? styles.sizeLg
          : size === "icon"
            ? styles.sizeIcon
            : styles.sizeDefault;

    return (
      <Comp
        className={cn(styles.button, variantClass, sizeClass, className)}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button };
