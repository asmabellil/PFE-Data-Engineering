from jobinsight.collectors.api_sources import (
    AdzunaCollector,
    ArbeitnowCollector,
    FranceTravailCollector,
    JobicyCollector,
    RemotiveCollector,
)
from jobinsight.collectors.pythonorg_scraper import PythonOrgScraper
from jobinsight.collectors.wttj_sitemap import WelcomeToTheJungleSitemap

#: registre des sources – ajouter une source = ajouter une classe ici (architecture modulaire)
COLLECTORS = {
    c.name: c
    for c in (
        ArbeitnowCollector,
        JobicyCollector,
        RemotiveCollector,
        PythonOrgScraper,
        WelcomeToTheJungleSitemap,
        AdzunaCollector,
        FranceTravailCollector,
    )
}

__all__ = ["COLLECTORS"]
