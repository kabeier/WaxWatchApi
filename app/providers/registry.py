from app.providers.discogs import DiscogsClient
from app.providers.mock import MockProvider

PROVIDERS = {
    "discogs": DiscogsClient,
    "mock": MockProvider,
}
