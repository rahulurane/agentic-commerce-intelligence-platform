import { defaultLogoUrl } from "../../brand/logo";

interface Props {
  /** Override the logo URL (null forces the text wordmark). Defaults to the brand slot. */
  logoUrl?: string | null;
}

/** Brand slot: the official logo when supplied, otherwise a text wordmark. */
export default function BrandMark({ logoUrl }: Props) {
  const url = logoUrl === undefined ? defaultLogoUrl : logoUrl;
  return (
    <div className="brand-mark" data-tour="brand">
      {url ? (
        <>
          <img src={url} alt="Global Payments" />
          <span className="brand-mark__word">ACIP</span>
        </>
      ) : (
        <>
          <span className="brand-mark__word">ACIP</span>
          <span className="brand-mark__co">
            in partnership with
            <br />
            Global Payments
          </span>
        </>
      )}
    </div>
  );
}
