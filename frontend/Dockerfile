# --- build stage ---
FROM node:20-alpine AS build
WORKDIR /app

# Install deps separately for layer caching
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./
ARG VITE_API_ORIGIN="http://localhost:8080"
ENV VITE_API_ORIGIN=${VITE_API_ORIGIN}
RUN npm run build

# --- runtime stage ---
FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
