from __future__ import annotations

from aiohttp import web

import main as base
import main_dev29 as dev29
import main_dev30 as dev30
import main_dev31 as dev31
import main_dev32 as dev32
import main_mcp
from causal_recorder_dev33 import RelevantCausalRecorder
from cover_episode_investigator import CoverEpisodeInvestigator

VERSION = "0.2.0-dev.33"


def _patch_dev33_card() -> None:
    dev32._patch_dev32_card()
    dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace("dev.32", "dev.33")
    dev29._CAUSAL_SCRIPT = dev29._CAUSAL_SCRIPT.replace("dev.32", "dev.33")

    marker = (
        "<li><strong>Volets à position partielle :</strong> un changement de <code>current_position</code> "
        "est rattaché au début du même mouvement uniquement si une trace exécutée prouve la commande "
        "<code>cover.set_cover_position</code> vers exactement cette position.</li>"
    )
    addition = (
        marker
        + "<li><strong>Événement pertinent :</strong> si un même <code>state_changed</code> produit à la fois "
          "un changement d'état et un changement d'attribut, une question générale privilégie l'état principal ; "
          "une valeur ou un attribut explicitement demandé reste prioritaire.</li>"
        + "<li><strong>Ouverture / fermeture des volets :</strong> les lignes répétées <code>opening</code> ou "
          "<code>closing</code> pendant le déplacement sont traitées comme un seul bloc cohérent, ancré sur son début.</li>"
    )
    if marker in dev29._CAUSAL_CARD and "Événement pertinent" not in dev29._CAUSAL_CARD:
        dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace(marker, addition, 1)


async def create_app() -> web.Application:
    # Élise Why remains frozen on dev.18. Dev.33 changes only Investigator's
    # local journal selection and deterministic cover episode correlation.
    dev31.VERSION = VERSION
    dev30.VERSION = VERSION
    dev29.VERSION = VERSION
    main_mcp.VERSION = VERSION

    # main_dev29 resolves these globals when it constructs the journal runtime.
    # Both replacements preserve the same public interfaces and remain read-only.
    dev29.CausalRecorder = RelevantCausalRecorder
    dev29.V02Investigator = CoverEpisodeInvestigator
    dev29.recorder_first_ask = dev31.journal_first_ask
    base.investigate = dev31.stable_investigate

    _patch_dev33_card()
    main_mcp.BASE_INDEX_HTML = dev31._patch_manual_ui_route(main_mcp.BASE_INDEX_HTML)

    app = await dev29.create_app()
    base.add_ingress_post(app, "/api/v1/investigate/deep", dev30.manual_investigate)
    base.add_ingress_post(app, "/api/v1/why", dev31.stable_investigate)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
