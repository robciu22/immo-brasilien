BOT_NAME = "immo-brasilien"
SPIDER_MODULES = ["scrapers"]
NEWSPIDER_MODULE = "scrapers"

ROBOTSTXT_OBEY = True
DOWNLOAD_DELAY = 2
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = 1
AUTOTHROTTLE_ENABLED = True

FEEDS = {
    "output/inserate_%(time)s.jsonl": {
        "format": "jsonlines",
        "encoding": "utf8",
    }
}

LOG_LEVEL = "INFO"
