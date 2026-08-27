from kncompanyscraper.repositories.base_repository import BaseRepository


class ScrapeRunRepository(BaseRepository):

    def start(self):
        query = """
            INSERT INTO scrape_runs (status)
            VALUES ('running')
            RETURNING id
        """

        with self._get_cursor() as cursor:
            cursor.execute(query)
            scrape_run_id = cursor.fetchone()[0]

        return scrape_run_id

    def complete(self, scrape_run_id, status, companies_found, news_added):
        query = """
            UPDATE scrape_runs
            SET finished_at = NOW(),
                status = %s,
                companies_found = %s,
                news_added = %s
            WHERE id = %s
        """

        with self._get_cursor() as cursor:
            cursor.execute(
                query,
                (
                    status,
                    companies_found,
                    news_added,
                    scrape_run_id
                )
            )

    def fail(self, scrape_run_id, error, companies_found, news_added):
        query = """
            UPDATE scrape_runs
            SET finished_at = NOW(),
                status = 'failed',
                error_message = %s,
                companies_found = %s,
                news_added = %s
            WHERE id = %s
        """

        with self._get_cursor() as cursor:
            cursor.execute(
                query,
                (
                    error,
                    companies_found,
                    news_added,
                    scrape_run_id
                )
            )
