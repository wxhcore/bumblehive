import { useCallback, useEffect, useRef, useState } from "react";

export function useToast(durationMilliseconds = 2_200) {
  const [message, setMessage] = useState("");
  const timerRef = useRef<number | null>(null);

  const notify = useCallback(
    (nextMessage: string) => {
      setMessage(nextMessage);
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
      }
      timerRef.current = window.setTimeout(
        () => setMessage(""),
        durationMilliseconds,
      );
    },
    [durationMilliseconds],
  );

  useEffect(
    () => () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
      }
    },
    [],
  );

  return { message, notify };
}
