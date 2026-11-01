#!/usr/bin/env bash
# Refuses unless exactly one credential mode is given: the App (client id + private key) or a token.
# Env (never interpolated): CLIENT_ID KEY_SET TOKEN_SET (the last two are "true" or "false").
set -eo pipefail

app=false
if [ -n "$CLIENT_ID" ] || [ "$KEY_SET" = "true" ]; then app=true; fi
if [ "$app" = "true" ] && [ "$TOKEN_SET" = "true" ]; then
  echo "::error::pass the App or github-token, not both"
  exit 1
fi
if [ "$app" = "false" ] && [ "$TOKEN_SET" != "true" ]; then
  echo "::error::no credentials: pass the App (client-id and its private key) or github-token"
  exit 1
fi
if [ "$KEY_SET" = "true" ] && [ -z "$CLIENT_ID" ]; then
  echo "::error::App incomplete: missing client-id"
  exit 1
fi
if [ -n "$CLIENT_ID" ] && [ "$KEY_SET" != "true" ]; then
  echo "::error::App incomplete: missing private key"
  exit 1
fi
