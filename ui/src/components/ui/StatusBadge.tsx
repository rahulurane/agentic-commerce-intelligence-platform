import type { Decision } from "../../api/types";
import { decisionColor, decisionIcon, decisionLabel } from "../../decision";
import Icon from "./Icon";

interface Props {
  decision: Decision | null | undefined;
  /** Optional prefix such as "Expected". */
  prefix?: string;
}

/** Decision chip: icon + word + tint, so colour is never the only signal. */
export default function StatusBadge({ decision, prefix }: Props) {
  return (
    <span className={`badge ${decisionColor(decision)}`}>
      <Icon name={decisionIcon(decision)} size={14} />
      {prefix ? `${prefix} ` : ""}
      {decisionLabel(decision)}
    </span>
  );
}
