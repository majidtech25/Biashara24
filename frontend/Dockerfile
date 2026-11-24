# Build the React app, then serve it with Caddy, which also forwards API calls
# to the backend and gets HTTPS certificates automatically.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Empty: the browser calls the API on the same address the app is served from.
ENV VITE_API_URL=""
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
