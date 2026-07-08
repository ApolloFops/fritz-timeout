from scripts.tools.utility import getCachePath

PLUGIN_CACHE_PATH = getCachePath("timeout")

# ===== CONFIG =====
LOG_COMPONENT = "Timeout"

DATABASE_PATH = PLUGIN_CACHE_PATH + "/timeout.db"
