import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import ThemeProvider from "./theme/ThemeProvider";
import "./styles/brand.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/components.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
