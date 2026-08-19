import schedule
import time

from kncompanyscraper.logger import get_logger
from kncompanyscraper import config
from kncompanyscraper.borsdata.client import BorsdataClient
from kncompanyscraper.benchmark_client import NasdaqBenchmarkClient
from kncompanyscraper.borsdata.ingestion import BorsdataIngestionService
from kncompanyscraper.borsdata.instrument_mapping import BorsdataInstrumentMappingService
from kncompanyscraper.jobs.borsdata_insider_job import BorsdataInsiderJob
from kncompanyscraper.jobs.borsdata_job import BorsdataJob
from kncompanyscraper.jobs.benchmark_sync_job import BenchmarkSyncJob
from kncompanyscraper.jobs.news_job import NewsJob
from kncompanyscraper.jobs.comparative_ranking_job import ComparativeRankingJob
from kncompanyscraper.jobs.ranking_performance_job import RankingPerformanceJob
from kncompanyscraper.jobs.ranking_challenger_performance_job import (
    RankingChallengerPerformanceJob,
)
from kncompanyscraper.analysis.ranking_challenger_performance import (
    RankingChallengerPerformanceEvaluator,
)
from kncompanyscraper.analysis.ranking_performance import RankingPerformanceEvaluator
from kncompanyscraper.repositories.analysis_repository import AnalysisRepository
from kncompanyscraper.repositories.agent_cohort_repository import AgentCohortRepository
from kncompanyscraper.repositories.company_repository import CompanyRepository
from kncompanyscraper.repositories.dividend_repository import DividendRepository
from kncompanyscraper.repositories.financial_repository import FinancialRepository
from kncompanyscraper.repositories.job_repository import JobRepository
from kncompanyscraper.repositories.insider_repository import InsiderRepository
from kncompanyscraper.repositories.news_repository import NewsRepository
from kncompanyscraper.repositories.valuation_repository import ValuationRepository
from kncompanyscraper.repositories.benchmark_repository import BenchmarkRepository
from kncompanyscraper.repositories.ranking_repository import RankingRepository
from kncompanyscraper.repositories.ranking_challenger_repository import (
    RankingChallengerRepository,
)
from kncompanyscraper.repositories.thesis_challenge_repository import (
    ThesisChallengeRepository,
)
from kncompanyscraper.scraper.notifier import Notifier
from kncompanyscraper.repositories.scrape_run_repository import ScrapeRunRepository

logger = get_logger(__name__)
repository = CompanyRepository()
news_repository = NewsRepository()
scrape_run_repository = ScrapeRunRepository()
notifier = Notifier()


def run_borsdata_once():
    client = BorsdataClient()
    companies = repository.get_active_companies()
    BorsdataInstrumentMappingService(client, repository).map_companies(companies)
    companies = repository.get_active_companies()
    job = BorsdataJob(
        BorsdataIngestionService(
            client,
            FinancialRepository(),
            ValuationRepository(),
            DividendRepository(),
        ),
        JobRepository(),
    )
    return job.run(companies)


def run_borsdata_insiders_once():
    companies = repository.get_active_companies()
    return BorsdataInsiderJob(
        BorsdataClient(),
        InsiderRepository(),
        JobRepository(),
    ).run(companies)


def run_comparative_ranking_once():
    return ComparativeRankingJob(
        AnalysisRepository(),
        ThesisChallengeRepository(),
        RankingRepository(),
        AgentCohortRepository(),
    ).run()


def run_ranking_performance_once():
    rankings = RankingRepository()
    return RankingPerformanceJob(
        rankings,
        RankingPerformanceEvaluator(
            ValuationRepository(),
            BenchmarkRepository(),
            DividendRepository(),
        ),
    ).run()


def run_ranking_challenger_performance_once():
    challengers = RankingChallengerRepository()
    return RankingChallengerPerformanceJob(
        challengers,
        RankingChallengerPerformanceEvaluator(
            ValuationRepository(),
            BenchmarkRepository(),
            DividendRepository(),
        ),
    ).run()


def run_benchmark_sync_once():
    result = BenchmarkSyncJob(
        NasdaqBenchmarkClient(),
        BenchmarkRepository(),
    ).run()
    logger.info(
        "OMXS30GI sync stored %d values through %s.",
        result.synced_count,
        result.stored_through,
    )
    if result.omitted_zero_dates:
        logger.warning(
            "OMXS30GI sync omitted zero-value dates: %s.",
            ", ".join(str(value) for value in result.omitted_zero_dates),
        )
    return result


def run_once():

    scrape_run_id = scrape_run_repository.start()

    companies_found = 0
    news_added = 0

    try:

        companies = repository.get_active_companies()
        companies_found = len(companies)

        jobs = [
            NewsJob(
                news_repository,
                notifier
            )
        ]

        for company in companies:
            for job in jobs:
                result = job.run(company)
                news_added += result

        scrape_run_repository.complete(
            scrape_run_id,
            "success",
            companies_found,
            news_added
        )

    except Exception as e:

        scrape_run_repository.fail(
            scrape_run_id,
            str(e),
            companies_found,
            news_added
        )

        raise

def configure_schedule():
    schedule.every(config.SCRAPE_INTERVAL_MINUTES).minutes.do(run_once)
    schedule.every().day.at(config.BORSDATA_SYNC_TIME).do(run_borsdata_once)
    schedule.every().day.at(config.BORSDATA_INSIDER_SYNC_TIME).do(run_borsdata_insiders_once)
    schedule.every().day.at(config.COMPARATIVE_RANKING_TIME).do(
        run_comparative_ranking_once
    )
    schedule.every().day.at(config.BENCHMARK_SYNC_TIME).do(run_benchmark_sync_once)
    schedule.every().day.at(config.RANKING_PERFORMANCE_TIME).do(
        run_ranking_performance_once
    )
    schedule.every().day.at(config.RANKING_PERFORMANCE_TIME).do(
        run_ranking_challenger_performance_once
    )


def start():
    logger.info(
        "Scheduler starting. News every %d minutes; Börsdata daily at %s; "
        "insiders at %s; comparative ranking check at %s; "
        "benchmark sync at %s; performance at %s.",
        config.SCRAPE_INTERVAL_MINUTES,
        config.BORSDATA_SYNC_TIME,
        config.BORSDATA_INSIDER_SYNC_TIME,
        config.COMPARATIVE_RANKING_TIME,
        config.BENCHMARK_SYNC_TIME,
        config.RANKING_PERFORMANCE_TIME,
    )

    run_once()
    configure_schedule()

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    start()
