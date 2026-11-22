import type { components } from "./api.generated";

/** `Schema<"PrismRead">` -> generated Pydantic response/request type. */
export type Schema<Name extends keyof components["schemas"]> = components["schemas"][Name];
export type { components, paths, operations } from "./api.generated";
