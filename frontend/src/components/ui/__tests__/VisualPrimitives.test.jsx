import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import Button from "../Button";
import Card from "../Card";

describe("shared visual primitives", () => {
  it("preserves enabled, disabled, and loading button behavior", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Save Changes</Button>);

    const button = screen.getByRole("button", { name: /save changes/i });
    expect(button).toBeEnabled();
    expect(button).not.toHaveAttribute("aria-busy");
    await user.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);

    rerender(<Button onClick={onClick} disabled>Save Changes</Button>);
    expect(button).toBeDisabled();
    await user.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);

    rerender(<Button onClick={onClick} loading>Saving Changes...</Button>);
    expect(screen.getByRole("button", { name: /saving changes/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /saving changes/i })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Saving Changes...")).toBeVisible();
  });

  it("keeps static cards non-interactive while forwarding existing interactive-card behavior", async () => {
    const onClick = vi.fn();
    const onKeyDown = vi.fn();
    const { rerender } = render(<Card>Static workforce summary</Card>);

    expect(screen.getByText("Static workforce summary")).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();

    rerender(
      <Card hover role="button" tabIndex={0} onClick={onClick} onKeyDown={onKeyDown}>
        Existing interactive card
      </Card>
    );

    const interactiveCard = screen.getByRole("button", { name: /existing interactive card/i });
    await userEvent.click(interactiveCard);
    fireEvent.keyDown(interactiveCard, { key: "Enter" });
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onKeyDown).toHaveBeenCalledTimes(1);
  });
});
