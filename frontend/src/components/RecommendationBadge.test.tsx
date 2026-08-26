import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RecommendationBadge, TierBadge } from "./RecommendationBadge";

describe("RecommendationBadge", () => {
  it("renders the human-readable label for each recommendation", () => {
    render(<RecommendationBadge recommendation="strong_apply" />);
    expect(screen.getByText("Strong Apply")).toBeInTheDocument();
  });

  it("renders Low Priority correctly", () => {
    render(<RecommendationBadge recommendation="low_priority" />);
    expect(screen.getByText("Low Priority")).toBeInTheDocument();
  });
});

describe("TierBadge", () => {
  it("renders the human-readable label for each evidence tier", () => {
    render(<TierBadge tier="explicit" />);
    expect(screen.getByText("Explicit match")).toBeInTheDocument();
  });

  it("renders no_evidence as 'No evidence'", () => {
    render(<TierBadge tier="no_evidence" />);
    expect(screen.getByText("No evidence")).toBeInTheDocument();
  });
});
