import * as React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const Spinner = React.forwardRef(({ className, size = "default", ...props }, ref) => {
  const sizeClasses = {
    xs: "h-3 w-3",
    sm: "h-4 w-4",
    default: "h-6 w-6",
    lg: "h-8 w-8",
  };

  return (
    <Loader2
      ref={ref}
      className={cn("animate-spin", sizeClasses[size], className)}
      {...props}
    />
  );
});
Spinner.displayName = "Spinner";

export { Spinner };
