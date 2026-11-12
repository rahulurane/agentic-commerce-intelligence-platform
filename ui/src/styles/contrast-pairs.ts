// Foreground/background pairs that must stay WCAG AA. Mirrors the values in brand.css
// and tokens.css: update this list whenever you swap a colour there, and the contrast
// test fails if a re-skin breaks AA. `min` is 4.5 for text and 3 for non-text graphics.
export interface ContrastPair {
  name: string;
  fg: string;
  bg: string;
  min: 3 | 4.5;
}

export const CONTRAST_PAIRS: ContrastPair[] = [
  // Light theme
  { name: "light primary text", fg: "#12263F", bg: "#FFFFFF", min: 4.5 },
  { name: "light muted text", fg: "#4A5D75", bg: "#F4F7FA", min: 4.5 },
  { name: "light heading", fg: "#003B71", bg: "#FFFFFF", min: 4.5 },
  { name: "light link", fg: "#00639A", bg: "#FFFFFF", min: 4.5 },
  { name: "light link on page", fg: "#00639A", bg: "#F4F7FA", min: 4.5 },
  { name: "light teal text", fg: "#0B7A5C", bg: "#FFFFFF", min: 4.5 },
  { name: "light teal text on page", fg: "#0B7A5C", bg: "#F4F7FA", min: 4.5 },
  { name: "light teal graphic", fg: "#129B75", bg: "#FFFFFF", min: 3 },
  { name: "light primary button", fg: "#FFFFFF", bg: "#003B71", min: 4.5 },
  { name: "light primary button hover", fg: "#FFFFFF", bg: "#00639A", min: 4.5 },
  { name: "light approve", fg: "#1B7A34", bg: "#FFFFFF", min: 4.5 },
  { name: "light approve on tint", fg: "#1B7A34", bg: "#E8F5EC", min: 4.5 },
  { name: "light challenge", fg: "#8A5A00", bg: "#FFFFFF", min: 4.5 },
  { name: "light challenge on tint", fg: "#8A5A00", bg: "#FFF4D6", min: 4.5 },
  { name: "light decline", fg: "#B42318", bg: "#FFFFFF", min: 4.5 },
  { name: "light decline on tint", fg: "#B42318", bg: "#FDECEA", min: 4.5 },
  { name: "light control border", fg: "#6F8399", bg: "#FFFFFF", min: 3 },
  // Dark theme
  { name: "dark control border", fg: "#5F7FAB", bg: "#12263F", min: 3 },
  { name: "dark primary text", fg: "#E8EEF5", bg: "#12263F", min: 4.5 },
  { name: "dark muted text", fg: "#9FB3C8", bg: "#12263F", min: 4.5 },
  { name: "dark link", fg: "#6DB7EA", bg: "#12263F", min: 4.5 },
  { name: "dark link on page", fg: "#6DB7EA", bg: "#0B1726", min: 4.5 },
  { name: "dark teal", fg: "#3FC9A0", bg: "#12263F", min: 4.5 },
  { name: "dark primary button", fg: "#0B1726", bg: "#6DB7EA", min: 4.5 },
  { name: "dark approve", fg: "#4ADE80", bg: "#12263F", min: 4.5 },
  { name: "dark approve on tint", fg: "#4ADE80", bg: "#12301F", min: 4.5 },
  { name: "dark challenge", fg: "#FBBF24", bg: "#12263F", min: 4.5 },
  { name: "dark challenge on tint", fg: "#FBBF24", bg: "#33260A", min: 4.5 },
  { name: "dark decline", fg: "#F87171", bg: "#12263F", min: 4.5 },
  { name: "dark decline on tint", fg: "#F87171", bg: "#3A1512", min: 4.5 },
];
