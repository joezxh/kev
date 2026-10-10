"use client";

import { useEffect, useRef } from "react";
import { cn } from "cn";

/**
 * Terminal-ish log viewer. Auto-scrolls to the end when new lines arrive,
 * but only if the user was already near the bottom — scrolling back to
 * read history should not be yanked away mid-line.
 */
export function LogStream({
  lines,
  isStreaming = false,
  maxHeight = "h-64",
  emptyHint,
}: {
  lines: string[];
  isStreaming?: boolean;
  maxHeight?: string;
  emptyHint?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  // Run before paint of the next render: remember whether the user was
  // parked near the bottom before the lines array changes.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const distanceFromBottom =
      node.scrollHeight - node.scrollTop - node.clientHeight;
    stickToBottomRef.current = distanceFromBottom < 24;
  });

  // After lines paint, snap to the bottom if we had been glued.
  useEffect(() => {
    const node = containerRef.current;
    if (!node || !stickToBottomRef.current) return;
    node.scrollTop = node.scrollHeight;
  }, [lines]);

  return (
    <div
      ref={containerRef}
      className={cn(
        "overflow-y-auto rounded-md border border-border bg-[#0a0a0a] p-3",
        maxHeight,
      )}
    >
      {lines.length === 0 ? (
        <div className="font-mono text-xs text-muted-foreground">
          {emptyHint ?? ""}
        </div>
      ) : (
        <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-foreground/90">
          {lines.join("\n")}
        </pre>
      )}
      {isStreaming && (
        <span
          aria-hidden
          className="mt-2 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[#3b82f6]"
        />
      )}
    </div>
  );
}