# Demo Containers

This repository exists to serve multiple Vandalizer instances behind a reverse proxy, for use in ./demo-containers/preloader.Dockerfile

It relies on three environment variables:

- `VANDALIZER_INSTANCE_NUMBER`: A number which identifies the vandalizer instance - used for some state and for explicit volume and network separation. This in particular reserves the local IP space `10.20.VANDALIZER_INSTANCE_NUMBER.0/24`. Defaults to 0, must be less than `256` to reserve an IP-space.
- `VANDALIZER_PORT_NUMBER`: The port this instance should serve from. Defaults to `8000`.
- `OPENAI_API_KEY`: An OpenAI API Key to pass downstream to Vandalizer.

# Deploying

The compose file pulls containers from Github Container Registry. It does not need the repository cloned, but you do need to have GHCR permissions on the `ui-iids/vandalizer` repository in your docker login.

With a Github account with appropriate permissions, create a [Github Personal Access Tokens (classic)](https://github.com/settings/tokens/new) with permission `read:packages`.

Perform `docker login ghcr.io` to log in, using the token as your password.

Download `compose.yaml` and run `docker compose up`; e.g.

```bash
export VANDALIZER_INSTANCE_NUMBER=5;
export VANDALIZER_PORT_NUMBER=5005;
export OPENAI_API_KEY=<this_is_secret>;
docker compose up;
```

# Networks

To avoid conflicting with AirVandalGold and other networks, this is set to explicitly reserve IPs for each pod in `10.20`. Change or remove that setting in the network if necessary.
