// Picks up the official logo if one has been dropped into src/assets/brand/ as
// logo.svg or logo.png. Nothing is shipped there and the logo is never redrawn.
const found = import.meta.glob("../assets/brand/logo.{svg,png}", {
  eager: true,
  query: "?url",
  import: "default",
}) as Record<string, string>;

export const defaultLogoUrl: string | undefined = Object.values(found)[0];
