from __future__ import annotations

from aiohttp import web

import main as base
import main_dev29 as dev29
import main_dev30 as dev30
import main_dev31 as dev31
import main_mcp
from cover_position_investigator import CoverPositionInvestigator

VERSION = "0.2.0-dev.32"


def _patch_dev32_card() -> None:
    # Reuse the dev.31 architecture wording, then apply only the dev.32 delta.
    dev31._patch_dev31_card()
    dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace("dev.31", "dev.32")
    dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace(
        "<strong>Ce que dev.29 change dans l'usage :</strong>",
        "<strong>Ce que dev.32 garantit dans l'usage :</strong>",
    )
    marker = "<li><strong>Action directe :</strong> la réponse indique l'utilisateur ; Alexa n'est citée que si cette provenance est réellement prouvée.</li>"
    addition = (
        marker
        + "<li><strong>Volets à position partielle :</strong> un changement de <code>current_position</code> "
          "est rattaché au début du même mouvement uniquement si une trace exécutée prouve la commande "
          "<code>cover.set_cover_position</code> vers exactement cette position.</li>"
    )
    if marker in dev29._CAUSAL_CARD and "Volets à position partielle" not in dev29._CAUSAL_CARD:
        dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace(marker, addition, 1)
    dev29._CAUSAL_SCRIPT = dev29._CAUSAL_SCRIPT.replace("dev.31", "dev.32")


async def create_app() -> web.Application:
    # Élise Why remains frozen on dev.18 and continues to call the historical
    # /api/v1/investigate endpoint. Dev.32 changes only Investigator's causal engine.
    dev31.VERSION = VERSION
    dev30.VERSION = VERSION
    dev29.VERSION = VERSION
    main_mcp.VERSION = VERSION

    dev29.V02Investigator = CoverPositionInvestigator
    dev29.recorder_first_ask = dev31.journal_first_ask
    base.investigate = dev31.stable_investigate

    _patch_dev32_card()
    main_mcp.BASE_INDEX_HTML = dev31._patch_manual_ui_route(main_mcp.BASE_INDEX_HTML)

    app = await dev29.create_app()
    base.add_ingress_post(app, "/api/v1/investigate/deep", dev30.manual_investigate)
    base.add_ingress_post(app, "/api/v1/why", dev31.stable_investigate)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
