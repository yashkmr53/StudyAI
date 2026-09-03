FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Local Compose is HTTP localhost: a service worker would pin the previous
# bundle. Production images can build with --build-arg VITE_DISABLE_PWA=0.
ARG VITE_DISABLE_PWA=1
ENV VITE_DISABLE_PWA=$VITE_DISABLE_PWA
RUN npm run build \
    && if [ "$VITE_DISABLE_PWA" = "1" ]; then rm -f dist/sw.js dist/registerSW.js dist/workbox-*.js; fi

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
