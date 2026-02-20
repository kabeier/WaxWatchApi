from __future__ import annotations

import random
from typing import Any

from app.providers.base import ProviderClient, ProviderListing


class MockProvider(ProviderClient):
    """
    Dev-only provider:
    returns deterministic-ish fake listings based on keywords.
    """
    name = "mock"

    def search(self, *, query: dict[str, Any], limit: int = 20) -> list[ProviderListing]:
        keywords = query.get("keywords") or []
        kws = [str(k).strip().lower() for k in keywords if str(k).strip()]

        # A couple curated “realistic” titles so matching actually demonstrates value
        base_titles = [
            "Primus - Sailing the Seas of Cheese (Vinyl)",
            "Primus - Frizzle Fry LP Vinyl",
            "Les Claypool - Of Whales and Woe (Vinyl)",
            "Radiohead - OK Computer (Vinyl)",
            "Miles Davis - Kind of Blue (Vinyl)",
        ]

        def pick_title() -> str:
            # If keywords exist, try to include them
            if kws:
                if "primus" in kws:
                    return random.choice(base_titles[:3])
                if "vinyl" in kws:
                    return random.choice(base_titles)
            return random.choice(base_titles)

        results: list[ProviderListing] = []
        must_match = False
        max_price = query.get("max_price")
        if isinstance(max_price, (int, float)) and "primus" in kws and "vinyl" in kws:
            must_match = True
            forced_price = float(max_price) - 0.01

        for i in range(min(limit, 5)):
            title = pick_title()
            price = round(random.uniform(15, 120), 2)

            if must_match and i == 0:
                title = "Primus - Sailing the Seas of Cheese (Vinyl)"
                price = round(forced_price, 2)
            else:
                price = round(random.uniform(15, 120), 2)

            results.append(
                ProviderListing(
                    provider="ebay", 
                    external_id=f"mock-{random.randint(100000, 999999)}",
                    url=f"https://example.com/mock/{random.randint(100000, 999999)}",
                    title=title,
                    price=price,
                    currency="USD",
                    condition=random.choice([None, "VG", "VG+", "NM"]),
                    seller=random.choice([None, "some_seller", "vinyl_shop_42"]),
                    location=random.choice([None, "US", "NC, USA"]),
                    discogs_release_id=None,
                    raw={"mock": True, "query": query},
                )
            )

        return results