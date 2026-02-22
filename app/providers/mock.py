from __future__ import annotations

import random
from typing import Any

from app.providers.base import ProviderClient, ProviderListing


class MockProvider(ProviderClient):
    """
    Dev-only provider:
    deterministic results per rule/query so repeated runs are stable and idempotent.
    """

    name = "mock"

    def search(self, *, query: dict[str, Any], limit: int = 20) -> list[ProviderListing]:
        keywords = query.get("keywords") or []
        kws = [str(k).strip().lower() for k in keywords if str(k).strip()]

        # Deterministic seed
        # Pass _seed from runner as rule.id string.
        seed = str(query.get("_seed") or "default")
        rng = random.Random(seed)

        max_price = query.get("max_price")
        base_titles = [
            "Primus - Sailing the Seas of Cheese (Vinyl)",
            "Primus - Frizzle Fry LP Vinyl",
            "Les Claypool - Of Whales and Woe (Vinyl)",
            "Radiohead - OK Computer (Vinyl)",
            "Miles Davis - Kind of Blue (Vinyl)",
        ]

        def pick_title() -> str:
            if "primus" in kws:
                return rng.choice(base_titles[:3])
            if "vinyl" in kws:
                return rng.choice(base_titles)
            return rng.choice(base_titles)

        results: list[ProviderListing] = []

        n = min(limit, 5)
        seed_short = seed.split("-")[0]

        for i in range(n):
            if i == 0 and isinstance(max_price, (int | float)) and "primus" in kws and "vinyl" in kws:
                title = "Primus - Sailing the Seas of Cheese (Vinyl)"
                price = round(float(max_price) - 0.01, 2)
            else:
                title = pick_title()
                price = round(rng.uniform(15, 120), 2)

            results.append(
                ProviderListing(
                    provider=self.name,
                    external_id=f"mock-{seed_short}-{i}",
                    url=f"https://example.com/mock/{seed_short}/{i}",
                    title=title,
                    price=price,
                    currency="USD",
                    condition=rng.choice([None, "VG", "VG+", "NM"]),
                    seller=rng.choice([None, "some_seller", "vinyl_shop_42"]),
                    location=rng.choice([None, "US", "NC, USA"]),
                    discogs_release_id=None,
                    raw={"mock": True, "seed": seed, "query": query},
                )
            )

        return results


class MockDiscogsClient(MockProvider):
    """
    Mock that behaves like the 'discogs' provider.
    """

    name = "discogs"
