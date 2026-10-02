# Render builds this file from the public result repository (Docker runtime, context deploy/).
# Render passes service environment variables to Docker builds as build arguments, so the service
# variable DEMO_IMAGE pins the exact published demo image, for example
#   ghcr.io/stephensookra/twin-pocketful-judged-demo:<first 12 characters of the packaging commit>
# Never set it to the latest tag: the deployed image must be the one its commit built and smoke tested.
ARG DEMO_IMAGE
FROM ${DEMO_IMAGE}
