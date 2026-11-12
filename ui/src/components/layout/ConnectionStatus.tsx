import { useCallback, useEffect, useState } from "react";
import { getHealth } from "../../api/client";
import InfoTip from "../ui/InfoTip";
import Icon from "../ui/Icon";

type Conn = "checking" | "connected" | "unreachable";

const POLL_MS = 15000;

/** Pill showing whether checkout-api answers /healthz. Re-checks every 15 s while visible. */
export default function ConnectionStatus() {
  const [state, setState] = useState<Conn>("checking");

  const check = useCallback(async () => {
    try {
      await getHealth();
      setState("connected");
    } catch {
      setState("unreachable");
    }
  }, []);

  useEffect(() => {
    void check();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") {
        void check();
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [check]);

  function retry() {
    setState("checking");
    void check();
  }

  return (
    <div className="conn" role="status" aria-live="polite">
      {state === "checking" && <span className="conn__pill checking">Checking</span>}
      {state === "connected" && (
        <span className="conn__pill connected">
          <Icon name="check-circle" size={14} />
          Connected
        </span>
      )}
      {state === "unreachable" && (
        <>
          <span className="conn__pill unreachable">
            <Icon name="x-circle" size={14} />
            Cannot reach checkout-api
          </span>
          <InfoTip
            term="connection problem"
            text="Start the platform with ./start.sh or ./start-local.sh, then press Retry. Check http://localhost:8080/healthz."
          />
          <button type="button" className="btn btn--sm" onClick={retry}>
            Retry
          </button>
        </>
      )}
    </div>
  );
}
