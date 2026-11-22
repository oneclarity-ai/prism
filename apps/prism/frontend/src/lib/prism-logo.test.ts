import { describe, expect, it } from "vitest";
import { PRISM_COLORS, prismColorKey, prismLogoMarkup } from "./prism-logo";

describe("prismColorKey", () => {
  it("keeps a valid chosen colour", () => {
    expect(prismColorKey({ color: "teal", name: "x" })).toBe("teal");
  });
  it("derives a stable colour from the name otherwise", () => {
    const first = prismColorKey({ name: "Research Prism" });
    expect(prismColorKey({ name: "Research Prism", color: "not-a-colour" })).toBe(first);
    expect(PRISM_COLORS.map((c) => c.key)).toContain(first);
    expect(prismColorKey(null)).toBe(PRISM_COLORS[0].key);
    expect(prismColorKey({ id: "abc" })).toBe(prismColorKey({ id: "abc" }));
  });
});

describe("prismLogoMarkup", () => {
  it("returns a standalone svg with unique gradient ids", () => {
    const a = prismLogoMarkup("blue");
    const b = prismLogoMarkup("blue");
    expect(a).toMatch(/^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" viewBox="0 0 200 200" aria-hidden="true">/);
    expect(a.match(/id="(pl\d+)tl"/)?.[1]).not.toBe(b.match(/id="(pl\d+)tl"/)?.[1]);
    expect(prismLogoMarkup("purple")).toContain("#4A5CF5");
    expect(prismLogoMarkup("nonsense")).toContain("#4A5CF5");
  });
});
