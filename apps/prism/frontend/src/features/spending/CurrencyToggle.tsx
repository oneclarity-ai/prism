import { costStore, useCostSnapshot, type Currency } from "./costStore";

/** The ₹/$ switch shown on the Spending page and in Preferences (`[data-currency]`). */
export function CurrencyToggle() {
  const { currency } = useCostSnapshot();
  const choices: ReadonlyArray<readonly [Currency, string]> = [
    ["INR", "₹ INR"],
    ["USD", "$ USD"],
  ];
  return (
    <span className="currency-toggle" role="group" aria-label="Currency">
      {choices.map(([value, label]) => (
        <button key={value} type="button" data-currency={value} aria-pressed={currency === value} onClick={() => costStore.setCurrency(value)}>
          {label}
        </button>
      ))}
    </span>
  );
}
