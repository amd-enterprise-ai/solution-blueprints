// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";

import { cn } from "@/libs/utils";
import styles from "./Label.module.scss";

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root ref={ref} className={cn(styles.label, className)} {...props} />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label };
