# Multi-stage build for the ACIP demo UI.
#
# Stage 1 builds the static bundle with the pinned Node toolchain (no host Node needed).
# The checkout-api base URL is baked in at build time via VITE_CHECKOUT_API_URL.
# Stage 2 serves the bundle from nginx with SPA history fallback on port 80.
#
# Build context is the REPO ROOT (see deploy/docker-compose.yml demo-ui), so paths are
# prefixed with ui/.

FROM node:20-alpine AS build
WORKDIR /app

ARG VITE_CHECKOUT_API_URL=http://localhost:8080
ENV VITE_CHECKOUT_API_URL=${VITE_CHECKOUT_API_URL}

COPY ui/package.json ui/package-lock.json ./
RUN npm ci

COPY ui/ ./
RUN npm run build

FROM nginx:alpine AS runtime
COPY ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
