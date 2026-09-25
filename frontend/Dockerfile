# Stage 1: Build the React app
# Node 24 bundles npm 11, which is required to read this package-lock.json
# (see the note above `npm ci` below). Build-stage only — the runtime image
# is nginx, so this does not affect what is served.
FROM docker.io/library/node:24-alpine AS builder

WORKDIR /app

# Build-time configuration. Vite reads VITE_-prefixed env vars at compile
# time, so we accept these as build args and re-export them as ENV before
# `npm run build`. `.env` files are excluded from the build context via
# `.dockerignore`, so this is the only way the bundle picks them up.
ARG VITE_SENTRY_DSN
ARG VITE_SENTRY_ENVIRONMENT
ARG VITE_SENTRY_RELEASE
# `VERSION` is already passed by the release / build-container workflows;
# reuse it as the Sentry release identifier when one isn't supplied so
# errors group correctly per deploy.
ARG VERSION
# Source-map upload runs only when SENTRY_AUTH_TOKEN is non-empty (see
# vite.config.ts). Empty args make `npm run build` skip the upload and
# emit the same artifacts as before.
ARG SENTRY_AUTH_TOKEN
ARG SENTRY_ORG
ARG SENTRY_PROJECT
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN} \
    VITE_SENTRY_ENVIRONMENT=${VITE_SENTRY_ENVIRONMENT} \
    VITE_SENTRY_RELEASE=${VITE_SENTRY_RELEASE:-${VERSION}} \
    SENTRY_AUTH_TOKEN=${SENTRY_AUTH_TOKEN} \
    SENTRY_ORG=${SENTRY_ORG} \
    SENTRY_PROJECT=${SENTRY_PROJECT}

COPY package.json package-lock.json ./
# package-lock.json is generated with npm 11 (dev machines, dependabot);
# npm 10 (bundled with Node 22) rejects its optional-dep shape (@emnapi/*).
# Do NOT reintroduce `npm install -g npm@11` here: on the alpine image npm
# cannot overwrite itself in place, and it leaves the global install broken
# ("Cannot find module 'promise-retry'"), failing this build. Getting npm 11
# from the base image is the reliable way to pin it.
RUN npm ci

COPY . .
RUN npm run build

# Stage 2a: unprivileged variant (published as vandalizer-frontend-unprivileged;
# the Helm chart defaults to it). Runs as the image's non-root `nginx` user
# (uid 101) and listens on 8080, which satisfies Kubernetes restricted Pod
# Security and OpenShift SCCs without workarounds. Built only when explicitly
# targeted (`--target runtime-unprivileged`); this stage sits BEFORE the
# default `runtime` stage so a plain `docker build` still produces the
# root-nginx port-80 image that compose users expect.
FROM docker.io/nginxinc/nginx-unprivileged:alpine AS runtime-unprivileged

USER root
RUN apk add --no-cache curl
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# The shared nginx.conf listens on 80 for the default image; non-root nginx
# cannot bind it, so rewrite to this base image's conventional 8080.
RUN sed -i 's/listen 80;/listen 8080;/' /etc/nginx/conf.d/default.conf
# Numeric (the base image's nginx user) so Kubernetes' runAsNonRoot check can
# verify it without a runAsUser override.
USER 101:101

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost:8080/health || exit 1

CMD ["nginx", "-g", "daemon off;"]

# Stage 2b: Serve with nginx (default image: root nginx on port 80)
FROM docker.io/library/nginx:alpine AS runtime

RUN apk add --no-cache curl

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
