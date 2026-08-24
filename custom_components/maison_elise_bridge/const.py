from __future__ import annotations

DOMAIN = "maison_elise_bridge"

CONF_CLOUDHOOK_URL = "cloudhook_url"
CONF_INVESTIGATOR_SLUG = "investigator_slug"
CONF_INVESTIGATOR_TOKEN = "investigator_token"
CONF_WEBHOOK_ID = "webhook_id"

EXPECTED_SKILL_ID = "amzn1.ask.skill.e91d3c5a-4440-43c5-bcc1-c12e1c1d8052"

INVESTIGATOR_ASK_PATH = "/api/v1/ask"
INVESTIGATOR_ENTITIES_PATH = "/api/v1/entities"
INVESTIGATOR_PORT = 8099
INVESTIGATOR_SLUG_SUFFIX = "elise_investigator_02_test"

CONFIG_TEST_TIMEOUT_SECONDS = 4
REQUEST_TIMEOUT_SECONDS = 6
MAX_QUESTION_LENGTH = 500

NOTIFICATION_ID = "maison_elise_bridge_cloudhook"
