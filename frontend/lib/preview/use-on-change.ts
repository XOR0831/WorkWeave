import { useState } from "react";

/**
 * Runs `onChange` during render when `value` changes ("adjusting state when a prop changes",
 * react.dev/learn/you-might-not-need-an-effect). `onChange` may only set this component's state.
 */
export function useOnChange<T>(value: T, onChange: () => void) {
  const [prev, setPrev] = useState(value);
  if (!Object.is(prev, value)) {
    setPrev(value);
    onChange();
  }
}
