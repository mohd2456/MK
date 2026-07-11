import { describe, it, expect } from "vitest";
import { render, screen } from "./utils";

describe("test infrastructure", () => {
  it("renders with custom render utility", () => {
    render(<div data-testid="hello">Hello World</div>);
    expect(screen.getByTestId("hello")).toHaveTextContent("Hello World");
  });

  it("provides router context", () => {
    render(<a href="/test">Link</a>);
    expect(screen.getByText("Link")).toBeInTheDocument();
  });
});
