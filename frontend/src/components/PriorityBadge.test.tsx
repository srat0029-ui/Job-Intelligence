import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PriorityBadge } from "./RecommendationBadge";

describe("PriorityBadge", () => {
  it("renders 'Apply ASAP' for the top priority tier", () => {
    render(<PriorityBadge priority="apply_asap" />);
    expect(screen.getByText("Apply ASAP")).toBeInTheDocument();
  });

  it("renders 'Low Priority' for the bottom tier", () => {
    render(<PriorityBadge priority="low_priority" />);
    expect(screen.getByText("Low Priority")).toBeInTheDocument();
  });
});
