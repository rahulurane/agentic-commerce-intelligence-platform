/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CHECKOUT_API_URL?: string;
  readonly VITE_JAEGER_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
